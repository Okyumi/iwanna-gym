#!/usr/bin/env python3
"""Evaluate a PufferLib-trained policy through the SHARED discovery
evaluator (the same `evaluator.task_metrics` used for every other agent),
so PufferLib results are directly comparable to the reference numbers.

Self-verifying like scripts/puffer_smoke.py: if torch + PufferLib are
importable it loads the checkpoint, drives the reference discovery env with
the policy (observable obs, no privileged fields), and prints/writes the
milestone-15 evaluator records. Otherwise it prints the exact external
command and marks the eval UNVERIFIED here (torch is blocked in-sandbox).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _have(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--obs-mode", default="observable_vector")
    ap.add_argument("--out", default="build/puffer_eval/status.json")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    if not (_have("torch") and _have("pufferlib")):
        status = {
            "task": a.task, "verified": False,
            "blocker": "torch/pufferlib not importable (pypi blocked); the "
                       "trained checkpoint cannot be loaded here.",
            "external_command": (
                f"python scripts/puffer_eval.py --task {a.task} "
                f"--checkpoint {a.checkpoint}"),
            "eval_contract": "loads the policy, drives the reference "
                             "IWannaDiscoveryEnv in observable_vector, and "
                             "scores with evaluator.task_metrics + aggregate() "
                             "— identical metric path to every other agent.",
        }
        with open(a.out, "w") as f:
            json.dump(status, f, indent=2)
        print(json.dumps(status, indent=2))
        return

    # torch path: load the policy and score through the shared evaluator
    import torch  # noqa: F401
    from iwanna_gym.discovery import evaluator as E
    from iwanna_gym.discovery import registry as R
    reg = R.load_registry()
    spec = reg[a.task]
    # NOTE: the policy loader mirrors PufferLib's CleanRL checkpoint; the
    # exact class import is resolved on the training-capable machine.
    from puffer_iwanna_policy import load_policy  # provided alongside the run
    policy = load_policy(a.checkpoint)
    records = E.run_task(a.task, policy=policy, obs_mode=a.obs_mode,
                         registry=reg)
    print(json.dumps({"task": a.task, "verified": True,
                      "metrics": records}, indent=2))


if __name__ == "__main__":
    main()
