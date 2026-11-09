#!/usr/bin/env python3
"""score.py [JOBS_DIR]: score every trial in JOBS_DIR (default jobs/), as written by ./run.sh, and print per arm the
trials, runs fixed, tokens and estimated cost, then the ByteAsk/Codex CLI ratios on the tasks both arms ran.

A trial is fixed when Harbor's verifier gave reward 1 (every fail-to-pass test passes and every pass-to-pass test still
passes). Tokens (input, including cached input, and output) and cost at list prices come from the trial's
agent/usage.json, written by agent.py from every model call. Ratios are ratios of sums over the paired tasks, each arm's runs of a task averaged first. Python 3.8+,
standard library only."""
import collections
import glob
import json
import os
import re
import sys

JOBS = sys.argv[1] if len(sys.argv) > 1 else "jobs"
JOB = re.compile(r"^(codex|byteask|oracle|nop)-(.+)-\d{8}-\d{6}$")
ARMS = ("codex", "byteask", "oracle", "nop")


def trial(t):
    res = json.load(open(os.path.join(t, "result.json")))
    reward = ((res.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    u = {}
    p = os.path.join(t, "agent", "usage.json")
    if os.path.exists(p):
        u = json.load(open(p))
    return {"fixed": reward is not None and reward >= 1.0, "graded": reward is not None,
            "error": bool(res.get("exception_info")),
            "tokens": u.get("tokens", 0), "cost": u.get("cost_usd") or 0.0, "calls": u.get("turns", 0)}


def main():
    rows = []
    for res in sorted(glob.glob(os.path.join(JOBS, "*", "*", "result.json"))):
        t = os.path.dirname(res)
        m = JOB.match(os.path.basename(os.path.dirname(t)))
        if m:
            rows.append(dict(arm=m.group(1), task=m.group(2), **trial(t)))
    print(f"{len(rows)} trials in {JOBS}\n")
    if not rows:
        return
    by = collections.defaultdict(list)
    for r in rows:
        by[r["arm"]].append(r)
    print(f"{'arm':8s} {'trials':>6s} {'fixed':>6s} {'errors':>6s} {'tokens/run':>11s} {'cost/run':>9s}")
    for arm in ARMS:
        rs = by.get(arm)
        if not rs:
            continue
        n = len(rs)
        print(f"{arm:8s} {n:6d} {sum(r['fixed'] for r in rs):6d} {sum(r['error'] for r in rs):6d}"
              f" {sum(r['tokens'] for r in rs) / n / 1e3:10.0f}k ${sum(r['cost'] for r in rs) / n:8.3f}")
    cell = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        cell[r["task"]][r["arm"]].append(r)
    pairs = sorted(t for t in cell if cell[t]["codex"] and cell[t]["byteask"])
    if not pairs:
        print("\nno task run by both codex and byteask yet: no ratios")
        return
    mean = lambda t, a, k: sum(x[k] for x in cell[t][a]) / len(cell[t][a])
    print(f"\nByteAsk / Codex CLI on the {len(pairs)} task(s) both ran:")
    for k, name in (("fixed", "fixed"), ("tokens", "tokens"), ("cost", "cost")):
        cx, bx = sum(mean(t, "codex", k) for t in pairs), sum(mean(t, "byteask", k) for t in pairs)
        if k == "fixed":
            print(f"  {name:9s} {bx:.1f} against {cx:.1f} (mean runs fixed per task, summed)")
        elif cx:
            print(f"  {name:9s} x{bx / cx:.3f}  ({100 * (bx / cx - 1):+.1f}%)")


if __name__ == "__main__":
    main()
