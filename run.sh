#!/usr/bin/env bash
# run.sh ARM TASK [JOBS_DIR]: one trial of the paper's setup, through Harbor.
#   ARM   codex | byteask | oracle | nop        TASK  a task from tasks.tsv (name or code), fetched with ./get_tasks.sh
# codex    Codex CLI 0.164.0 as shipped. Needs OPENAI_API_KEY (passed to the task's API proxy only).
# byteask  the ByteAsk CLI with ByteAsk Context. Needs BYTEASK_SIGNIN_DIR (see the README).
# oracle   applies the reference fix (reward 1); nop changes nothing (reward 0). No key needed.
# Both agent arms run GPT-6.1 Sol at medium reasoning effort (MODEL, EFFORT), with the same instruction, time limit
# (45 minutes), 3 CPUs and 5 GB of memory. Needs docker (compose v2, buildx) and harbor 0.25.0.
set -euo pipefail
arm=$1 task=$2 jobs=${3:-jobs}
here=$(cd "$(dirname "$0")" && pwd)
case "$task" in [HP][0-9][0-9]) task=$(awk -v c="$task" '$1 == c {print $2}' "$here/tasks.tsv");; esac
src=$arm; case "$arm" in oracle|nop) src=codex;; esac
dir="$here/tasks/$task/$src"
[ -d "$dir" ] || { echo "no $dir: run ./get_tasks.sh $task first" >&2; exit 1; }
export MODEL=${MODEL:-gpt-6.1-sol} EFFORT=${EFFORT:-medium} HARBOR_TELEMETRY=0 PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}"
case "$arm" in
  codex)
    : "${OPENAI_API_KEY:?set OPENAI_API_KEY}"
    # the real key goes only to the api-proxy container (compose interpolation); the agent gets a dummy key
    export UPSTREAM_API_KEY="$OPENAI_API_KEY"; unset OPENAI_API_KEY OPENAI_BASE_URL CODEX_API_KEY
    agent=(-a agent:CodexCLI);;
  byteask)
    : "${BYTEASK_SIGNIN_DIR:?set BYTEASK_SIGNIN_DIR}"
    agent=(-a agent:ByteAskCLI);;
  oracle|nop) agent=(-a "$arm");;
  *) echo "unknown arm $arm" >&2; exit 2;;
esac
exec harbor run -q -y -p "$dir" "${agent[@]}" -n 1 -o "$jobs" --job-name "$arm-$task-$(date +%Y%m%d-%H%M%S)"
