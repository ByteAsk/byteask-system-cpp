"""Harbor agents for the two arms of byteask-system-cpp. Both run GPT-6.1 Sol at medium reasoning effort on the task's
instruction, as the agent user in /app, with no approval prompts (the container is the sandbox), and record the token
usage of every model call in the trial's agent log (usage.json).

  CodexCLI    Codex CLI 0.164.0 as shipped (baked into the task's codex image), through the task's API proxy.
  ByteAskCLI  the ByteAsk CLI (baked into the task's byteask image with the public installer) with ByteAsk Context:
              your ByteAsk sign-in is copied in, indexing is turned on without asking, then `byteask exec` runs the
              task.

Use with: PYTHONPATH=. harbor run -p tasks/TASK/ARM -a agent:CodexCLI | agent:ByteAskCLI ... (see run.sh)."""
import json
import os
import shlex
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

MODEL = os.environ.get("MODEL", "gpt-6.1-sol")
EFFORT = os.environ.get("EFFORT", "medium")
# list prices, $ per 1M tokens: uncached input, cached input, output
PRICE = {"gpt-6.1-sol": (2.00, 0.10, 10.00)}
LOG = "/logs/agent"


def usage_from_events(text):
    """Sum the usage of every completed turn in a `codex exec --json` / `byteask exec --json` event stream."""
    tot = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "turns": 0}
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "turn.completed" and isinstance(ev.get("usage"), dict):
            u = ev["usage"]
            tot["turns"] += 1
            for k in ("input_tokens", "cached_input_tokens", "output_tokens"):
                tot[k] += int(u.get(k) or 0)
    p = PRICE.get(MODEL)
    if p:
        tot["cost_usd"] = round(((tot["input_tokens"] - tot["cached_input_tokens"]) * p[0]
                                 + tot["cached_input_tokens"] * p[1] + tot["output_tokens"] * p[2]) / 1e6, 6)
    tot["tokens"] = tot["input_tokens"] + tot["output_tokens"]
    return tot


class _Arm(BaseAgent):
    def __init__(self, logs_dir, model_name=None, **kwargs):
        super().__init__(logs_dir=logs_dir, model_name=model_name, **kwargs)

    def version(self) -> str:
        return "1.0.0"

    async def _sh(self, env, cmd, timeout=600, user="agent", envs=None):
        r = await env.exec(command=cmd, timeout_sec=timeout, user=user, env=envs)
        return r.return_code, (r.stdout or "") + (r.stderr or "")

    async def _finish(self, env, context, events_path):
        rc, text = await self._sh(env, f"cat {events_path} 2>/dev/null || true", timeout=120, user="root")
        u = usage_from_events(text)
        context.n_input_tokens, context.n_cache_tokens, context.n_output_tokens = (
            u["input_tokens"], u["cached_input_tokens"], u["output_tokens"])
        context.cost_usd = u.get("cost_usd")
        Path(self.logs_dir).mkdir(parents=True, exist_ok=True)
        (Path(self.logs_dir) / "usage.json").write_text(json.dumps(dict(u, model=MODEL, effort=EFFORT), indent=1))

    def _exec_flags(self):
        return (f"--skip-git-repo-check --json --dangerously-bypass-approvals-and-sandbox -C /app "
                f"-m {shlex.quote(MODEL)} -c model_reasoning_effort={shlex.quote(json.dumps(EFFORT))} "
                f"-c tools.web_search=false")


class CodexCLI(_Arm):
    """Codex CLI 0.164.0, as shipped. Its API key is a dummy: the task's proxy holds the real one."""

    @staticmethod
    def name() -> str:
        return "codex-cli"

    async def setup(self, environment: BaseEnvironment) -> None:
        pass

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        home = f"{LOG}/codex-home"
        await self._sh(environment, f"mkdir -p {home} && chown agent:agent {home}", user="root")
        # Codex's own provider setting for an OpenAI-compatible endpoint: the task's API proxy (it holds the real key)
        cfg = ('model_provider = "api-proxy"\n\n[model_providers.api-proxy]\nname = "OpenAI through the task API proxy"\n'
               'base_url = "http://api-proxy:8080/v1"\nenv_key = "OPENAI_API_KEY"\nwire_api = "responses"\n')
        await self._sh(environment, f"cat > {home}/config.toml <<'EOF'\n{cfg}EOF")
        events = f"{LOG}/events.jsonl"
        cmd = (f"codex exec {self._exec_flags()} -- {shlex.quote(instruction)} > {events} 2> {LOG}/stderr.txt")
        rc, _ = await self._sh(environment, cmd, timeout=2700,
                               envs={"CODEX_HOME": home, "OPENAI_API_KEY": "dummy-agent-key"})
        await self._sh(environment, f"echo {rc} > {LOG}/exit_code", user="root")
        await self._finish(environment, context, events)


class ByteAskCLI(_Arm):
    """The ByteAsk CLI with ByteAsk Context, set up as https://byteask.ai/install and https://byteask.ai/context say.

    Needs, on the host (see the README): BYTEASK_SIGNIN_DIR, a ByteAsk home where you ran `byteask login` and
    `byteask context connect` once. Its sign-in files are copied into the container; they are not written to the
    trial's logs."""

    @staticmethod
    def name() -> str:
        return "byteask-cli"

    async def setup(self, environment: BaseEnvironment) -> None:
        src = os.environ.get("BYTEASK_SIGNIN_DIR")
        if not src or not Path(src).is_dir():
            raise RuntimeError("set BYTEASK_SIGNIN_DIR to the ByteAsk home you signed in with (see the README)")
        for name in ("config.toml", "auth.json", ".credentials.json", "gateway"):
            p = Path(src) / name
            if p.is_file():
                await environment.upload_file(source_path=p, target_path=f"/home/agent/.byteask/{name}")
        await self._sh(environment, "chown -R agent:agent /home/agent/.byteask && chmod 600 /home/agent/.byteask/*",
                       user="root")

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        task = "/opt/byteask/task.json"
        # 1. ByteAsk Context's prerequisites (https://byteask.ai/context/setup): a git origin remote and a
        #    compile_commands.json from the project's own CMake configure (the options the tests build with)
        prep = (f"cd /app && url=$(python3 -c 'import json; print(json.load(open(\"{task}\"))[\"repo_url\"])') && "
                "(git remote get-url origin >/dev/null 2>&1 || git remote add origin \"$url\") && "
                f"args=$(python3 -c 'import json, shlex; print(\" \".join(map(shlex.quote, json.load(open(\"{task}\"))[\"cmake_args\"])))') && "
                "eval cmake -S /app -B /app/build/byteask -DCMAKE_EXPORT_COMPILE_COMMANDS=ON $args "
                f"> {LOG}/configure.log 2>&1")
        await self._sh(environment, prep, timeout=1800)
        # 2. index without asking (`byteask context auto-index on`): the CLI indexes the repository with ByteAsk
        #    Context when the task starts
        await self._sh(environment, f"byteask context auto-index on > {LOG}/auto-index.log 2>&1")
        # 3. the task, with ByteAsk Context connected (from the sign-in)
        events = f"{LOG}/events.jsonl"
        cmd = (f"byteask exec {self._exec_flags()} -- {shlex.quote(instruction)} > {events} 2> {LOG}/stderr.txt")
        rc, _ = await self._sh(environment, cmd, timeout=2700, envs={"BYTEASK_NO_UPDATE_CHECK": "1"})
        await self._sh(environment, f"echo {rc} > {LOG}/exit_code", user="root")
        await self._finish(environment, context, events)
