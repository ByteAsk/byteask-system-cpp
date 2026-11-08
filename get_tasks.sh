#!/usr/bin/env bash
# get_tasks.sh [TASK...]: download tasks from the repository's tasks-v1 release into tasks/ (all of tasks.tsv by default).
# TASK is a task name or code (H01, P07). Each archive holds one repository snapshot at its base commit (app.tar, plus
# deps.tar for tasks with build dependencies) and one Harbor task folder per arm (codex, byteask); the snapshot is
# linked into every folder whose Dockerfile needs it.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
base=${TASKS_URL:-https://github.com/ByteAsk/byteask-system-cpp/releases/download/tasks-v1}
mkdir -p "$here/tasks" "$here/.cache"
[ -f "$here/.cache/SHA256SUMS" ] || curl -fsSL "$base/SHA256SUMS" -o "$here/.cache/SHA256SUMS"
tasks=("$@"); [ ${#tasks[@]} -gt 0 ] || mapfile -t tasks < <(awk 'NR > 1 {print $2}' "$here/tasks.tsv")
for t in "${tasks[@]}"; do
  case "$t" in [HP][0-9][0-9]) t=$(awk -v c="$t" '$1 == c {print $2}' "$here/tasks.tsv");; esac
  f="$here/.cache/$t.tar.gz"
  [ -f "$f" ] || curl -fL --retry 3 "$base/$t.tar.gz" -o "$f"
  (cd "$here/.cache" && grep " $t.tar.gz\$" SHA256SUMS | sha256sum -c --quiet -) || { echo "checksum mismatch: $t" >&2; exit 1; }
  rm -rf "$here/tasks/$t" && tar -xzf "$f" -C "$here/tasks"
  for d in "$here/tasks/$t"/*/; do
    for sub in environment tests; do
      for a in app.tar deps.tar; do
        if [ -f "$d$sub/Dockerfile" ] && grep -q "source=$a" "$d$sub/Dockerfile"; then ln -f "$here/tasks/$t/$a" "$d$sub/$a"; fi
      done
    done
  done
  echo "$t: $(ls -d "$here/tasks/$t"/*/ | xargs -n1 basename | tr '\n' ' ')"
done
