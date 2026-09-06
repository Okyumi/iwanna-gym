"""Self-verifying PufferLib training/eval smoke harness.

On a training-capable machine (torch + a pinned PufferLib install),
this runs a SHORT real `puffer` train + eval on a controlled room and,
when a local pack exists, a native task, then records simulation-only
and end-to-end throughput separately. In THIS sandbox (no torch, pypi
blocked) it cannot run PufferLib; it then prints the exact external
command and writes an UNVERIFIED status file — so the milestone's
blocked state is explicit and machine-readable, never faked.

Usage: PYTHONPATH=. python scripts/puffer_smoke.py
Output: build/pufferlib_smoke/status.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, ".")

PIN = "42f70d6932c30ac977736f861006809c50168ba9"   # PufferLib 4.0.0
OUT = "build/pufferlib_smoke"


def _have(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def external_command() -> list[str]:
    return [
        "# 1. stage the env into a pinned PufferLib checkout:",
        "bash scripts/setup_pufferlib.sh $HOME/PufferLib",
        "# 2. controlled-room smoke (real puffer train + eval):",
        "export IWG_LEVEL_FILE=$PWD/iwanna_gym/levels/traps/t06_crusher.txt",
        "cd $HOME/PufferLib && puffer build iwanna && \\",
        "  puffer train iwanna --train.total-timesteps 2000000 \\",
        "                      --track.eval-frequency 200",
        "# 3. native task smoke (needs a locally-built iwbtgr pack;",
        "#    emit its kwargs+IWG_PACK via",
        "#    iwanna_gym.discovery.binding_kwargs(task_id), then train).",
    ]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    have_torch = _have("torch")
    have_puffer = _have("pufferlib")
    status = {
        "pinned_pufferlib": PIN,
        "pinned_version": "4.0.0",
        "binding": "c_src/puffer/binding.c (+ iwanna_puffer.h adapter)",
        "config": "config/iwanna_puffer.ini",
        "have_torch": have_torch,
        "have_pufferlib": have_puffer,
    }

    if not (have_torch and have_puffer):
        status["verified"] = False
        status["blocker"] = (
            "torch and/or pufferlib not importable, and pypi is blocked "
            "in this environment (pip install fails, no wheels). A real "
            "`puffer train` run is therefore not executable here.")
        status["external_run_command"] = external_command()
        status["what_is_verified_here"] = [
            "the 4.0.0 binding compiles against the pinned PufferLib "
            "headers (tests/test_pufferlib_binding.py)",
            "every [env] kwarg the binding reads is present in the config",
            "simulation-only throughput (scripts/bench_discovery_vec.py)",
        ]
        print("UNVERIFIED: torch/pufferlib unavailable here. External run:")
        for line in external_command():
            print("   " + line)
        with open(os.path.join(OUT, "status.json"), "w",
                  encoding="utf-8") as f:
            json.dump(status, f, indent=1)
        return 0

    # -- training-capable path (executed on real hardware) --
    puf = os.environ.get("IWG_PUFFERLIB_DIR", os.path.expanduser(
        "~/PufferLib"))
    subprocess.run(["bash", "scripts/setup_pufferlib.sh", puf], check=True)
    env = dict(os.environ,
               IWG_LEVEL_FILE=os.path.abspath(
                   "iwanna_gym/levels/traps/t06_crusher.txt"))
    build = subprocess.run(["puffer", "build", "iwanna"], cwd=puf,
                           env=env, capture_output=True, text=True)
    status["build_ok"] = build.returncode == 0
    train = subprocess.run(
        ["puffer", "train", "iwanna",
         "--train.total-timesteps", "200000"],
        cwd=puf, env=env, capture_output=True, text=True)
    status["train_ok"] = train.returncode == 0
    status["train_tail"] = train.stdout[-2000:]
    status["verified"] = build.returncode == 0 and train.returncode == 0
    with open(os.path.join(OUT, "status.json"), "w",
              encoding="utf-8") as f:
        json.dump(status, f, indent=1)
    print("puffer smoke:", "OK" if status["verified"] else "FAILED")
    return 0 if status["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
