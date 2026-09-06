"""Pre-registered discovery pilot (docs/discovery_pilot_prereg.md).

Trains the matched policy set on each pilot suite and evaluates with
the milestone-15 metric definitions, retaining raw per-attempt records.
Configurations are fixed HERE (committed before results); nothing is
tuned after inspection.

    PYTHONPATH=. python scripts/run_pilot.py all
    PYTHONPATH=. python scripts/run_pilot.py P1 --policies gru gru_reset

Outputs: build/discovery_pilot/<pilot>/<policy>_s<seed>/
    checkpoint.npz  train_log.jsonl  summary.json  eval.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, ".")
import iwanna_gym.discovery as d                          # noqa: E402
from iwanna_gym.discovery import evaluator as E           # noqa: E402
from iwanna_gym.discovery.baselines import (PPOTrainer,   # noqa: E402
                                            TrainerEvalMemory)
from train_discovery import train                         # noqa: E402

OUT = os.path.join("build", "discovery_pilot")

ACTIVE_TRAIN = [
    "disc.research.t01_apple", "disc.research.t02_volley",
    "disc.research.t03_riser", "disc.research.t04_fall",
    "disc.research.t06_crusher", "disc.research.t10_chain",
    "disc.research.t12_gauntlet", "disc.research.t13_floorgate",
    "disc.research.t14_race",
]
ACTIVE_HOLDOUT = [
    "disc.research.t09_fakesave", "disc.research.t11_teleport",
    "disc.research.t17_wall",                       # validation
    "disc.research.t18_ladder", "disc.research.t20_finale",   # test
]
PRECISION = ["traps/t07_bullets", "traps/t15_rain",
             "traps/t16_bridge", "traps/t19_speedgate"]
NATIVE = ["disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall"]

BASE = dict(obs_mode="observable_vector", n_envs=24, rollout_T=128,
            hid=128, lr=3e-4, gamma=0.999, lam=0.95, clip=0.2,
            ent_coef=0.01, vf_coef=0.5, epochs=2, ckpt_every=50)

PILOTS = {
    "P1": dict(tasks=ACTIVE_TRAIN, budget=5_000_000, seeds=(1, 2, 3),
               eval_tasks=ACTIVE_TRAIN + ACTIVE_HOLDOUT,
               suite_label="controlled"),
    "P2": dict(tasks=[dict(level=r, K=25, H=2000) for r in PRECISION],
               budget=3_000_000, seeds=(1, 2),
               eval_tasks=[dict(level=r, K=25, H=2000)
                           for r in PRECISION],
               suite_label="precision_control"),
    "P3": dict(tasks=NATIVE, budget=3_000_000, seeds=(1, 2),
               eval_tasks=NATIVE, suite_label="iwbtg_native"),
}
POLICIES = ("ff", "gru", "gru_reset", "deathmem")
EVAL_TASK_SEEDS = (11, 12, 13)


# ------------------------------------------------------------------ #
# evaluation that handles registry ids AND raw precision rooms
# ------------------------------------------------------------------ #

def eval_checkpoint(ckpt: str, tasks, suite_label: str,
                    obs_mode="observable_vector") -> list[dict]:
    """Evaluate a trained checkpoint through the SHARED evaluator
    (E.run_task) — no duplicated loop, real trajectory indices, terminal
    events, and the corrected metrics."""
    tr = PPOTrainer.resume(ckpt)
    records = []
    for task in tasks:
        # tag raw precision rooms with the pilot's suite label/split
        if isinstance(task, dict):
            task = dict(task, suite=suite_label, split="n/a")
        for tseed in EVAL_TASK_SEEDS:
            mem = TrainerEvalMemory(tr)
            records.append(E.run_task(
                task, policy=lambda o, i, m: m.act(o), memory=mem,
                task_seed=tseed, obs_mode=obs_mode))
    return records


def run_pilot(pilot: str, policies=POLICIES, only_eval=False) -> None:
    P = PILOTS[pilot]
    for policy in policies:
        for seed in P["seeds"]:
            out = os.path.join(OUT, pilot, f"{policy}_s{seed}")
            cfg = dict(BASE, policy=policy, tasks=P["tasks"], seed=seed,
                       env_step_budget=P["budget"], headline=True)
            t0 = time.time()
            if not only_eval:
                s = train(cfg, out)
                print(f"[{pilot}] {policy} s{seed}: trained "
                      f"{s['env_steps']:,} steps in {s['wall_s']}s "
                      f"({s['overall_sps']:,} sps)", flush=True)
            recs = eval_checkpoint(os.path.join(out, "checkpoint.npz"),
                                   P["eval_tasks"], P["suite_label"])
            E.write_jsonl(recs, os.path.join(out, "eval.jsonl"))
            agg = E.aggregate(recs, K=25)
            with open(os.path.join(out, "eval_aggregate.json"), "w",
                      encoding="utf-8") as f:
                json.dump(agg, f, indent=1)
            print(f"[{pilot}] {policy} s{seed}: eval S@K="
                  f"{agg['success_at_K']['mean']:.3f} "
                  f"AUC={agg['auc']:.3f} gain={agg['adaptation_gain']:.3f}"
                  f" ({time.time()-t0:.0f}s total)", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pilot", choices=list(PILOTS) + ["all"])
    ap.add_argument("--policies", nargs="*", default=list(POLICIES))
    ap.add_argument("--only-eval", action="store_true")
    args = ap.parse_args()
    for p in (list(PILOTS) if args.pilot == "all" else [args.pilot]):
        run_pilot(p, args.policies, args.only_eval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
