# byteask-system-cpp

Code for **ByteAsk: Build-Aware Context and a Checking Harness for C++ Coding Agents** (Pratyush Saini, CTO,
ByteAsk Research, pratyush@byteask.ai; Anirudha Kulkarni, CEO, ByteAsk Research, anirudha@byteask.ai; November 2026).

ByteAsk is a coding agent for C and C++. ByteAsk Context understands code the way the project's build does and tells
the AI model where a change belongs, which related places may need the same change and which tests cover them. The
paper compares ByteAsk with OpenAI's Codex CLI 0.164.0 on the same model, GPT-6.1 Sol at medium effort. Both agents
fixed the same number of runs in every set (each: 44 of 46 in popular projects, 85 of 98 in little-known projects, 129 of
144 pooled, 9 of 15 hard issues). Per run:

| Task set | Runs | Tokens, Codex CLI / ByteAsk | Saving | Estimated cost, Codex CLI / ByteAsk | Saving |
|---|---|---|---|---|---|
| Issues in popular C++ projects (23 tasks, 2 runs each) | 46 | 727k / 263k | 63.9% | $0.227 / $0.092 | 59.9% |
| Issues in little-known C++ projects (49 tasks, 2 runs each) | 98 | 2,296k / 457k | 80.1% | $0.456 / $0.137 | 70.1% |
| Both sets pooled | 144 | 1,795k / 395k | 78.0% | $0.383 / $0.122 | 68.1% |
| Hard issues (5 tasks, 3 runs each) | 15 | 2,085k / 400k | 80.8% | $0.441 / $0.142 | 67.9% |

Paper: [byteask.ai/research/byteask-system-cpp](https://byteask.ai/research/byteask-system-cpp). The PDF is in this
repository: `paper.pdf`.

## Tasks

`tasks.tsv` lists the paper's 72 tasks: 23 issues in popular C++ projects (H01 to H23) and 49 issues in
little-known C++ projects (P01 to P49), with the 5 hard issues marked. Each row gives the task code, the task name, the repository and its base commit. Every task is in the [Harbor](https://github.com/laude-institute/harbor)
task format, one folder per arm:

- `instruction.md`: the paper's prompt and rules, with the issue text;
- `environment/`: the repository at its base commit (no later commits) with its build dependencies, and the agent;
- `tests/`: the maintainers' fail-to-pass and pass-to-pass tests, applied only when grading, in a separate container
  with no network. A task is fixed when every fail-to-pass test passes and every pass-to-pass test still passes;
- `solution/`: the reference fix.

```bash
./get_tasks.sh             # all 72 tasks from the tasks-v1 release (5.2 GB)
./get_tasks.sh H01 P07     # or some of them, by code or name
```

## Run it

You need Linux with Docker (compose v2 and buildx), 3 CPU cores and 5 GB of memory per trial, and Harbor 0.25.0
(`uv tool install harbor==0.25.0`). Both arms run GPT-6.1 Sol at medium reasoning effort with the same instruction,
a 45-minute limit and the same resources.

**Codex CLI.** Codex CLI 0.164.0 as shipped. Set `OPENAI_API_KEY` to a key with access to `gpt-6.1-sol`. The agent's
container has no network except an API proxy that holds the key and forwards only Responses API calls for the model.

```bash
export OPENAI_API_KEY=...
./run.sh codex H01
```

**ByteAsk.** The ByteAsk CLI, installed in the task image with the command from
[byteask.ai/install](https://byteask.ai/install), with [ByteAsk Context](https://byteask.ai/context). Sign in once on
your machine into a ByteAsk home of its own, connect ByteAsk Context, and point `BYTEASK_SIGNIN_DIR` at that home:

```bash
curl -fsSL https://code.byteask.ai/install.sh | sh
export BYTEASK_SIGNIN_DIR=$PWD/byteask-home
BYTEASK_HOME=$BYTEASK_SIGNIN_DIR byteask login --email you@example.com
BYTEASK_HOME=$BYTEASK_SIGNIN_DIR byteask context connect
./run.sh byteask H01
```

The sign-in files are copied into the trial's container. In the container the repository gets the two things ByteAsk
Context needs, an `origin` remote and a `compile_commands.json` from the project's own CMake configure, and indexing
is turned on (`byteask context auto-index on`). The agent's container reaches only `code.byteask.ai` and
`context.byteask.ai`.

**Check a task.** `./run.sh oracle H01` applies the reference fix (reward 1); `./run.sh nop H01` changes nothing
(reward 0). Each trial's result, logs and token usage (`agent/usage.json`) are in `jobs/`; `python3 score.py`
sums them up.

## The sample

Four tasks, two from each main set, each with a small checkout: `H01` (fastfloat/fast_float), `H07`
(jbeder/yaml-cpp), `P28` (mariusbancila/croncpp) and `P38` (tgockel/json-voorhees). One run of each task in both arms
is 8 trials:

```bash
./get_tasks.sh H01 H07 P28 P38           # about 16 MB
for t in H01 H07 P28 P38; do
  ./run.sh codex "$t"
  ./run.sh byteask "$t"
done
python3 score.py                         # fixed, tokens and cost per arm, ByteAsk/Codex CLI ratios
```

At the paper's mean cost per run ($0.383 for Codex CLI, $0.122 for ByteAsk), the 8 trials cost about $2 in API
usage. The first run of a task builds its images, which takes a few minutes. Run more tasks from `tasks.tsv`, or each
task more than once, for a steadier result.

## What to expect

The paper's result on all 72 tasks, 2 runs each: both agents fixed 129 of 144 runs. ByteAsk used 78.0% fewer tokens
(1,795k against 395k per run) at an estimated cost that was 68.1% lower ($0.383 against $0.122 per run). On the 5 hard issues both fixed 9 of 15 runs, with 80.8% fewer tokens and 67.9% lower
cost.

A sample of a few tasks will not match these numbers. Expect the same issues fixed by both agents and far fewer tokens
and lower cost for ByteAsk; the size of each ratio moves from run to run.

## Layout

```
tasks.tsv               the paper's tasks: code, name, set, repository, base commit
get_tasks.sh            download tasks from the tasks-v1 release into tasks/ and check them
run.sh                  one trial through Harbor: ./run.sh ARM TASK [JOBS_DIR]
agent.py                the Harbor agents of the two arms (Codex CLI, ByteAsk CLI)
score.py                score every trial in jobs/: fixed, tokens and cost per arm, and ByteAsk/Codex CLI ratios
paper.pdf               the paper
```

## Citation

```bibtex
@misc{saini2026byteasksystem,
  title        = {ByteAsk: Build-Aware Context and a Checking Harness for C++ Coding Agents},
  author       = {Saini, Pratyush and Kulkarni, Anirudha},
  year         = {2026},
  month        = nov,
  institution  = {ByteAsk Research},
  howpublished = {\url{https://byteask.ai/research/byteask-system-cpp}},
  note         = {Preprint. Code: \url{https://github.com/ByteAsk/byteask-system-cpp}}
}
```

## License

The scripts are MIT licensed (`LICENSE`). Each
repository snapshot in the tasks keeps its project's own license.
