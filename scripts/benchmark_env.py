"""Performance regression benchmark for the native core.

Measures pure-C stepping (random actions generated inside the C library via
``iw_bench``; no Python in the loop) across the scenarios the project
promises to protect:

    empty     — entity-free static room (the classic fast path)
    trap      — controlled trap room (t20_finale: entities + events)
    pack      — imported synthetic game pack (multi-room, flags, gate)
    heavy     — entity-heavy room (1000 oscillating spikeballs)

Usage:
    python scripts/benchmark_env.py [--steps N] [--repeat K] [--json out.json]

Compare against a saved baseline by eye or with --json in CI. Treat a
regression above ~10% on `empty` (best-of-K) as a problem to investigate,
per the performance-protection contract in docs/importer_architecture.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from iwanna_gym.clib import CIWanna                      # noqa: E402
from iwanna_gym.gamepack import compile_pack             # noqa: E402
from iwanna_gym.levels import load_level                 # noqa: E402
from tools.importers import synthetic                    # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "tests", "fixtures", "synthetic_src")


def heavy_level(n: int = 1000) -> str:
    rows = ["#" * 40] + ["#" + "." * 38 + "#" for _ in range(20)] + ["#" * 40]
    rows[19] = "#S" + "." * 37 + "#"
    lvl = "\n".join(rows) + "\n"
    lvl += "".join(f"@spikeball {5 + (i % 30)} {2 + (i // 30) % 15} vx=1 range=64\n"
                   for i in range(n))
    return lvl


def scenarios() -> dict[str, CIWanna]:
    pack = compile_pack(synthetic.extract(FIXTURE)).data
    sc = {
        "empty": CIWanna(load_level("flat"), seed=1),
        "trap": CIWanna(load_level("traps/t20_finale"), seed=1),
        "pack": CIWanna.from_pack(pack, seed=1, checkpoint_respawn=True),
        "heavy": CIWanna(heavy_level(), seed=1),
    }
    # exact-game scenarios when the locally built pack exists
    try:
        from iwanna_gym.games import iwbtgr_1_5_3 as G
        gp = G.load_pack()
        names = G.room_names()
        sc["iwbtgr_full"] = CIWanna.from_pack(
            gp, seed=1, checkpoint_respawn=True)
        sc["iwbtgr_room"] = CIWanna.from_pack(
            gp, seed=1, checkpoint_respawn=True,
            start_room=names.index("rGuyLabyrinth"))
    except FileNotFoundError:
        pass
    return sc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=2_000_000,
                    help="steps per scenario (heavy uses steps/10)")
    ap.add_argument("--repeat", type=int, default=3,
                    help="repetitions; best-of is reported")
    ap.add_argument("--json", help="write results to this JSON file")
    args = ap.parse_args()

    results = {}
    for name, c in scenarios().items():
        c.reset()
        steps = args.steps // 10 if name == "heavy" else args.steps
        best = 0.0
        for r in range(args.repeat):
            dt = c.bench(steps, seed=7 + r)
            best = max(best, steps / dt)
        results[name] = {"steps": steps, "best_msteps_per_s": best / 1e6}
        print(f"{name:8s} {best / 1e6:8.3f} M steps/s   (best of {args.repeat})")
        c.close()

    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
