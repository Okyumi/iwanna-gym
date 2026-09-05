"""Benchmark-workload throughput for the native vectorized path.

Measures env steps/second on the ACTUAL benchmark workloads — not
tile-only speed: controlled rooms, a representative source-native
IWBTGR non-boss room task, a dynamic/boss-heavy IWBTGR room, and a
mixed heterogeneous vector — plus the native-vector vs
reference-Gymnasium comparison on the same exact-game task.

Usage: PYTHONPATH=. python scripts/bench_discovery_vec.py [steps_per_env]
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, ".")
import iwanna_gym.discovery as d                          # noqa: E402
from iwanna_gym.discovery.vector import CVecIWanna        # noqa: E402

PACK = "build/games/iwbtgr_1_5_3.iwpack"
STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 20_000
N = 16


def bench(name: str, entries, obs_mode="observable_vector",
          steps=STEPS) -> float:
    v = CVecIWanna(entries, obs_mode=obs_mode, base_seed=3)
    v.reset()
    v.bench(min(steps // 10, 2000))                        # warmup
    secs = v.bench(steps)
    sps = v.n * steps / secs
    print(f"  {name:34s} n={v.n:3d}  {sps:12,.0f} env steps/s "
          f"({obs_mode})")
    v.close()
    return sps


def main() -> int:
    cores = os.cpu_count()
    print(f"cores={cores}; vector width N={N}; "
          f"steps/env={STEPS:,}; discovery protocol ON for all rows")
    bench("controlled trap rooms",
          ["disc.research.t06_crusher"] * N)
    if os.path.exists(PACK):
        bench("IWBTGR rGuy1 (1124-inst non-boss)",
              ["disc.iwbtgr_1_5_3.rGuy1.first_screen"] * N)
        bench("IWBTGR rGuyFortress1 (fire hall)",
              ["disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall"] * N)
        # dynamic/boss-heavy: the Kraidgief boss arena via a raw pack
        # entry (boss rooms are excluded from the discovery suites but
        # belong in the throughput picture)
        import iwanna_gym.games.iwbtgr_1_5_3 as G
        boss = dict(pack_path=os.environ.get("IWANNA_IWBTGR_PACK")
                    or G.PACK_PATH,
                    start_room=G.room_names().index("rKraidgiefBoss"),
                    K=25, H=2000, action_n=12)
        bench("IWBTGR rKraidgiefBoss (boss-heavy)", [boss] * N)
        mixed = (["disc.research.t06_crusher",
                  "disc.research.t12_gauntlet",
                  "disc.iwbtgr_1_5_3.rGuy1.first_screen",
                  "disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall"] * N)[:N]
        bench("mixed heterogeneous vector", mixed)
        bench("mixed (privileged obs)", mixed,
              obs_mode="privileged_vector")

        # native vector vs reference Gymnasium loop, same exact task
        tid = "disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall"
        v = CVecIWanna([tid] * N, base_seed=3)
        v.reset()
        secs = v.bench(STEPS)
        native = v.n * STEPS / secs
        v.close()
        env = d.make_env(tid)
        env.reset(seed=0, options={"task_seed": 3})
        rng = np.random.default_rng(0)
        t0 = time.monotonic()
        gym_steps = min(STEPS * 4, 60_000)
        for _ in range(gym_steps):
            env.step(int(rng.integers(0, 12)))
        gym_sps = gym_steps / (time.monotonic() - t0)
        env.close()
        print(f"\n  same-task comparison ({tid.split('.')[-1]}):")
        print(f"    native vector (1 C call/frame): {native:12,.0f} steps/s")
        print(f"    reference Gymnasium loop:       {gym_sps:12,.0f} steps/s"
              f"  ({native / gym_sps:.1f}x)")
    else:
        print(f"  ({PACK} absent: source-native rows skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
