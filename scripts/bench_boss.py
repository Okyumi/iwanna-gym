"""Boss-milestone benchmark scenarios.

    python scripts/bench_boss.py [--steps N] [--envs K]

Reports steps/s for:
  arena_birdo      active MechaBirdo fight (mixed 12-action policy)
  arena_kraidgief  active Kraidgief fight (touch the trigger, then mixed)
  parallel_boss    K parallel MechaBirdo arenas stepped round-robin
  parallel_normal  K parallel rGuy1 rooms (the same loop; the delta is
                   the boss layer's active cost, the absolute number the
                   many-env throughput)

The ordinary-room regression check (framework compiled but inactive) is
the interleaved A/B of scripts/benchmark_env.py between the pre-boss
commit and HEAD — see docs/boss_architecture.md "Performance".
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
from iwanna_gym.clib import CIWanna                      # noqa: E402
from iwanna_gym.games import iwbtgr_1_5_3 as G           # noqa: E402


def _mk(room, seed=7):
    c = CIWanna.from_pack(G.load_pack(), seed=seed, checkpoint_respawn=True,
                          start_room=G.room_names().index(room),
                          max_steps=1 << 30)
    c.reset()
    return c


def bench_arena(room, steps):
    c = _mk(room)
    t0 = time.perf_counter()
    for t in range(steps):
        c.step((t * 2654435761) % 12)
    dt = time.perf_counter() - t0
    c.close()
    return steps / dt


def bench_parallel(room, steps, k):
    envs = [_mk(room, seed=100 + i) for i in range(k)]
    t0 = time.perf_counter()
    for t in range(steps // k):
        a = (t * 2654435761) % 12
        for c in envs:
            c.step(a)
    dt = time.perf_counter() - t0
    for c in envs:
        c.close()
    return (steps // k) * k / dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=200000)
    ap.add_argument("--envs", type=int, default=64)
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()
    rows = []
    for name, fn in [
        ("arena_birdo", lambda: bench_arena("rMechaBirdoBoss", args.steps)),
        ("arena_kraidgief",
         lambda: bench_arena("rKraidgiefBoss", args.steps)),
        ("parallel_boss",
         lambda: bench_parallel("rMechaBirdoBoss", args.steps, args.envs)),
        ("parallel_normal",
         lambda: bench_parallel("rGuy1", args.steps, args.envs)),
    ]:
        best = max(fn() for _ in range(args.repeat))
        rows.append((name, best))
        print(f"{name:18s} {best:12,.0f} steps/s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
