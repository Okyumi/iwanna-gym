"""Overhead benchmark for the discovery runtime (milestone item 8).

Measures pure-C steps/s (iw_bench_n: random actions, no Python in the
loop — the same path the PufferLib binding drives) across:

  legacy        - discovery off, privileged obs (the historical path)
  obs_filter    - discovery off, observable obs (filtering cost only)
  discovery     - protocol on (K=25, H=2000), privileged obs
  disc+observ   - protocol on + observable obs (the headline config)

on a classic event-heavy trap room and, when the local source-built
pack exists, an IWBTGR room. The step path stays allocation-free: the
protocol adds integer bookkeeping and the filter adds branch tests in
the existing entity scan; any material regression is a bug to
investigate, not to hide.

Usage: PYTHONPATH=. python scripts/bench_discovery.py [steps]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")
from iwanna_gym.clib import CIWanna  # noqa: E402
from iwanna_gym.levels import load_level  # noqa: E402

STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
PACK = "build/games/iwbtgr_1_5_3.iwpack"


def bench(make, label: str, configure=None, steps: int = STEPS) -> float:
    c = make()
    if configure:
        configure(c)
    c.reset()
    c.bench_n(min(steps // 10, 100_000), seed=1)          # warmup
    secs = c.bench_n(steps, seed=7)
    sps = steps / secs
    print(f"  {label:14s} {sps:12,.0f} steps/s")
    c.close()
    return sps


def suite(name: str, make) -> None:
    print(f"{name}:")
    base = bench(make, "legacy")
    for label, cfg in (
        ("obs_filter", lambda c: c.set_obs_mode(1)),
        ("discovery", lambda c: c.set_discovery(25, 2000, 0)),
        ("disc+observ", lambda c: c.set_discovery(25, 2000, 1)),
    ):
        sps = bench(make, label, cfg)
        print(f"  {'':14s} {sps / base * 100:9.1f}% of legacy")


def main() -> None:
    trap = load_level("trap")
    suite("classic trap room (events + entities)",
          lambda: CIWanna(trap, max_steps=50_000, reward_mode=0,
                          death_penalty=1.0, seed=3))
    if os.path.exists(PACK):
        with open(PACK, "rb") as f:
            data = f.read()
        suite("iwbtgr rGuy1 (exact layer, 1124-instance room)",
              lambda: CIWanna(None, pack_data=data, max_steps=50_000,
                              reward_mode=0, death_penalty=1.0, seed=3,
                              checkpoint_respawn=True))
    else:
        print(f"({PACK} absent: pack suite skipped)")


if __name__ == "__main__":
    main()
