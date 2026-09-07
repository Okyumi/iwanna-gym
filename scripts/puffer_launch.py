#!/usr/bin/env python3
"""Single reproducible PufferLib launcher for ANY registered discovery task
(controlled OR native) — the complete command, not an outline.

It (1) resolves the task's numeric kwargs and file-path env vars from the
registry, (2) for a native task builds the source-derived pack from a LOCAL
source checkout if it is not already present (never committed), (3) writes a
task-specific 4.0.0 config with those kwargs baked into [env], and (4) emits
the exact `puffer build` / `puffer train` / evaluation command line, running
it unless --dry-run.

Usage:
    python scripts/puffer_launch.py <task_id> \
        --pufferlib-dir $HOME/PufferLib \
        [--source-checkout <iwbtgr source>] \
        [--timesteps 2000000] [--dry-run]

Examples (the two required paths):
    # controlled research room
    python scripts/puffer_launch.py disc.research.t06_crusher \
        --pufferlib-dir $HOME/PufferLib
    # native source-derived task (builds the pack from a local checkout)
    python scripts/puffer_launch.py \
        disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall \
        --pufferlib-dir $HOME/PufferLib \
        --source-checkout $HOME/IWBTGR-Autosplitter-mod

--dry-run does everything EXCEPT the torch steps (resolve paths, build the
pack, write the config, print the commands) so it is verifiable without
torch/PufferLib; the printed commands are the exact external run.
"""
from __future__ import annotations

import argparse
import configparser
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_CONFIG = "config/iwanna_puffer.ini"
PIN = "42f70d6932c30ac977736f861006809c50168ba9"


def _ensure_pack(task_id, source_checkout, dry):
    """Return the IWG_PACK path for a native task, building it from a local
    source checkout if absent. Controlled tasks return (None)."""
    import iwanna_gym.discovery as d
    reg = d.load_registry()
    spec = reg[task_id]
    if spec.suite != "iwbtg_native":
        return None
    kwargs, env = d.binding_kwargs(task_id, reg)
    pack = env["IWG_PACK"]
    if os.path.exists(pack):
        return pack
    if not source_checkout:
        raise SystemExit(
            f"native task needs pack {pack} which is absent; pass "
            f"--source-checkout <local {spec.game} source> to build it "
            f"(source is never committed).")
    cmd = [sys.executable, "-m", f"iwanna_gym.games.{spec.game}",
           "build", source_checkout]
    print("  building pack:", " ".join(cmd))
    if not dry:
        subprocess.run(cmd, check=True)
    return pack


def _write_config(task_id, out_path, timesteps):
    """Write a task-specific config: the committed base with [env] keys
    overwritten by the registry's binding kwargs for this task."""
    import iwanna_gym.discovery as d
    kwargs, env = d.binding_kwargs(task_id)
    cp = configparser.ConfigParser()
    cp.optionxform = str
    cp.read(BASE_CONFIG)
    for k, v in kwargs.items():
        cp["env"][k] = repr(v) if isinstance(v, float) else str(int(v))
    if timesteps:
        cp["train"]["total_timesteps"] = str(int(timesteps))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        cp.write(f)
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    ap.add_argument("--pufferlib-dir", default=os.environ.get(
        "IWG_PUFFERLIB_DIR", "$HOME/PufferLib"))
    ap.add_argument("--source-checkout", default=None)
    ap.add_argument("--timesteps", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    print(f"# PufferLib launch for {a.task_id}")
    print(f"# pinned PufferLib 4.0.0 @ {PIN}")

    # 1. stage the env into the pinned checkout
    setup = ["bash", "scripts/setup_pufferlib.sh", a.pufferlib_dir]
    print("1) stage env:", " ".join(setup))
    if not a.dry_run:
        subprocess.run(setup, check=True)

    # 2. resolve pack (native) / level, and env vars
    pack = _ensure_pack(a.task_id, a.source_checkout, a.dry_run)
    cfg_path = f"build/puffer_launch/{a.task_id}.ini"
    env = _write_config(a.task_id, cfg_path, a.timesteps)
    print(f"2) task config written: {cfg_path}")
    print(f"   env vars: {env}")

    # 3. the exact build/train/eval command line
    envline = " ".join(f'{k}="{v}"' for k, v in env.items())
    train = (f'cd {a.pufferlib_dir} && {envline} '
             f'IWG_CONFIG={os.path.abspath(cfg_path)} '
             f'puffer build iwanna && {envline} '
             f'IWG_CONFIG={os.path.abspath(cfg_path)} puffer train iwanna')
    evalcmd = (f'{envline} python scripts/puffer_eval.py --task {a.task_id} '
               f'--checkpoint <trained_checkpoint>   '
               f'# scores via the shared evaluator (evaluator.task_metrics)')
    print("3) build + train (needs torch + PufferLib):")
    print("   " + train)
    print("4) evaluate through the shared evaluator:")
    print("   " + evalcmd)

    if a.dry_run:
        print("\n[dry-run] resolved everything without torch; the two "
              "commands above are the exact external run.")
        return
    # real run requires torch/PufferLib; puffer is invoked by the shell line
    subprocess.run(train, shell=True, check=True)


if __name__ == "__main__":
    main()
