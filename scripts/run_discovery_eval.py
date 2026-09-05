"""Reference evaluator run: blind memoryless baselines over the ACTIVE
discovery tasks, per suite, with JSONL records and aggregates.

Usage:
    PYTHONPATH=. python scripts/run_discovery_eval.py [suite] [out_dir]

Suites are never pooled; oracle mode (--oracle) is the clearly-labeled
upper-bound diagnostic and lands in *.oracle.jsonl.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")
import iwanna_gym.discovery as d                        # noqa: E402
from iwanna_gym.discovery import evaluator as E         # noqa: E402


def sprint_policy(obs, info, memory):
    return 4


def hop_policy(obs, info, memory):
    hop = getattr(memory, "t", 0)
    memory.t = hop + 1
    return 5 if (hop % 24) < 6 else 4


class HopMemory(E.NullMemory):
    def reset_task(self):
        self.t = 0


def main() -> int:
    suite = sys.argv[1] if len(sys.argv) > 1 else "controlled"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "build/discovery_eval"
    oracle = "--oracle" in sys.argv
    reg = d.load_registry()
    tasks = d.suite_tasks(suite, reg, active_only=True)
    if not tasks:
        print(f"suite {suite!r} has no ACTIVE tasks")
        return 0
    for name, policy, mem_cls in (
            ("sprint", sprint_policy, E.NullMemory),
            ("hop_sprint", hop_policy, HopMemory)):
        records = []
        for spec in tasks:
            for seed in (1, 2, 3):
                records.append(E.run_task(
                    spec.task_id, policy, memory=mem_cls(),
                    task_seed=seed, oracle=oracle, registry=reg))
        path = E.write_jsonl(
            records, f"{out_dir}/{suite}.{name}.jsonl")
        agg = E.aggregate(records, K=tasks[0].attempts_K)
        print(f"\n== {suite} / {name}"
              + (" [ORACLE — not benchmark-eligible]" if oracle else ""))
        print(f"   tasks x seeds = {agg['n_task_runs']}; "
              f"Success@K = {agg['success_at_K']['mean']:.3f}"
              f" (sem {agg['success_at_K']['sem'] or 0:.3f})")
        print(f"   S(1) = {agg['s1']:.3f}  AUC = {agg['auc']:.3f}  "
              f"adaptation gain = {agg['adaptation_gain']:.3f}")
        rdr = agg["repeated_death_rate"]
        print(f"   repeated-death rate = "
              f"{rdr['mean'] if rdr['mean'] is not None else 'n/a'}")
        print(f"   wrote {path}")
        with open(f"{out_dir}/{suite}.{name}.aggregate.json", "w",
                  encoding="utf-8") as f:
            json.dump(agg, f, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
