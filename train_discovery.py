"""Discovery-benchmark baseline training on the native vectorized path.

Pure-numpy PPO (no RL framework, no Python-stepped vector env: every
frame is one C call across the batch). Reproducible configs live in
configs/discovery/*.json; launch commands:

    # scripted/random diagnostics (no learning):
    PYTHONPATH=. python scripts/run_discovery_eval.py controlled

    # feed-forward PPO on the active controlled suite:
    PYTHONPATH=. python train_discovery.py --config configs/discovery/ff_controlled.json

    # recurrent PPO, memory carried across attempt deaths:
    PYTHONPATH=. python train_discovery.py --config configs/discovery/gru_controlled.json

    # causal-reset ablation (identical except memory zeroed per death):
    PYTHONPATH=. python train_discovery.py --config configs/discovery/gru_reset_controlled.json

    # explicit episodic death-memory baseline:
    PYTHONPATH=. python train_discovery.py --config configs/discovery/deathmem_controlled.json

    # native-task headline smoke (needs the local source-built pack):
    PYTHONPATH=. python train_discovery.py --config configs/discovery/gru_native_smoke.json

Outputs under --out (default build/discovery_runs/<name>): checkpoint
(.npz, resumable via --resume), train_log.jsonl (per-iteration env
steps, SPS, finished-task outcomes) and eval.jsonl (evaluator-format
records via iwanna_gym.discovery.evaluator — consumable by
aggregate()). Oracle/privileged runs are tagged and refuse the
headline label.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from iwanna_gym.discovery import evaluator as E          # noqa: E402
from iwanna_gym.discovery.baselines import PPOTrainer    # noqa: E402


def train(cfg: dict, out_dir: str, resume: str | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    if cfg.get("headline") and cfg.get("obs_mode") == "privileged_vector":
        raise SystemExit("privileged_vector runs are ORACLE diagnostics "
                         "and cannot be labeled headline")
    tcfg = {k: v for k, v in cfg.items()
            if k in ("tasks", "policy", "obs_mode", "n_envs", "rollout_T",
                     "hid", "lr", "gamma", "lam", "clip", "ent_coef",
                     "vf_coef", "epochs", "seed")}
    tr = (PPOTrainer.resume(resume) if resume else PPOTrainer(**tcfg))
    budget = int(cfg["env_step_budget"])
    log_path = os.path.join(out_dir, "train_log.jsonl")
    mode = "a" if resume else "w"
    t0 = time.monotonic()
    steps0 = tr.env_steps
    with open(log_path, mode, encoding="utf-8") as log:
        while tr.env_steps < budget:
            it0 = time.monotonic()
            batch = tr.collect()
            tc0 = time.monotonic()
            tr.update(batch)
            it1 = time.monotonic()
            done = tr.finished_tasks
            tr.finished_tasks = []
            n_steps = tr.cfg["rollout_T"] * tr.cfg["n_envs"]
            rec = dict(
                iteration=tr.iteration,
                env_steps=tr.env_steps,
                wall_s=round(time.monotonic() - t0, 2),
                env_sps=round(n_steps / max(tc0 - it0, 1e-9)),
                learner_sps=round(n_steps / max(it1 - tc0, 1e-9)),
                end_to_end_sps=round(n_steps / max(it1 - it0, 1e-9)),
                tasks_finished=len(done),
                task_success_rate=(sum(d["success"] for d in done)
                                   / len(done) if done else None),
                mean_attempts=(sum(d["attempts"] for d in done)
                               / len(done) if done else None),
                oracle=tr.oracle,
            )
            log.write(json.dumps(rec) + "\n")
            log.flush()
            if tr.iteration % int(cfg.get("ckpt_every", 20)) == 0:
                tr.save(os.path.join(out_dir, "checkpoint.npz"))
    tr.save(os.path.join(out_dir, "checkpoint.npz"))
    wall = time.monotonic() - t0
    summary = dict(
        config=cfg, out_dir=out_dir,
        env_steps=tr.env_steps,
        wall_s=round(wall, 1),
        overall_sps=round((tr.env_steps - steps0) / max(wall, 1e-9)),
        oracle=tr.oracle,
    )
    with open(os.path.join(out_dir, "summary.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    return summary


def evaluate(cfg: dict, out_dir: str, n_seeds: int = 3) -> str:
    """Post-training evaluation through the milestone-15 evaluator
    (records consumable by evaluator.aggregate())."""
    from iwanna_gym.discovery.baselines import TrainerEvalMemory
    tr = PPOTrainer.resume(os.path.join(out_dir, "checkpoint.npz"))
    obs_mode = cfg.get("obs_mode", "observable_vector")
    records = []
    for tid in cfg["tasks"]:
        for seed in range(1, n_seeds + 1):
            mem = TrainerEvalMemory(tr)         # shared eval adapter
            records.append(E.run_task(
                tid, policy=lambda o, i, m: m.act(o), memory=mem,
                task_seed=seed, obs_mode=obs_mode, oracle=tr.oracle))
    return E.write_jsonl(records, os.path.join(out_dir, "eval.jsonl"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out")
    ap.add_argument("--resume")
    ap.add_argument("--eval", action="store_true",
                    help="run post-training evaluation only")
    args = ap.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    out = args.out or os.path.join(
        "build", "discovery_runs",
        os.path.splitext(os.path.basename(args.config))[0])
    if args.eval:
        path = evaluate(cfg, out)
        print(f"eval records: {path}")
        return 0
    summary = train(cfg, out, resume=args.resume)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
