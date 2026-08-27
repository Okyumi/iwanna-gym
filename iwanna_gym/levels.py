"""Level loading and procedural generation.

Text format (one char per 32x32 tile):
    '#' block, '^' 'v' '<' '>' spikes, 'S' start, 'G' goal, '.' or ' ' empty.
Standard fangame room is 25x19 tiles (800x608 px).
"""
from __future__ import annotations

import os
import random

from .clib import NUM_BUILTIN_LEVELS, builtin_level_text

_LEVEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "levels")

BUILTIN_NAMES = ["flat", "gaps", "needle", "tower"]


def list_levels() -> list[str]:
    names = list(BUILTIN_NAMES)
    if os.path.isdir(_LEVEL_DIR):
        for f in sorted(os.listdir(_LEVEL_DIR)):
            if f.endswith(".txt"):
                name = f[:-4]
                if name not in names:
                    names.append(name)
    return names


def load_level(name: str) -> str:
    """Load level text by name (builtin name, file in levels/, or path)."""
    if name in BUILTIN_NAMES:
        return builtin_level_text(BUILTIN_NAMES.index(name))
    for cand in (os.path.join(_LEVEL_DIR, name + ".txt"), name):
        if os.path.isfile(cand):
            with open(cand) as f:
                return f.read()
    raise FileNotFoundError(
        f"level {name!r} not found (builtins: {BUILTIN_NAMES}, dir: {_LEVEL_DIR})"
    )


assert NUM_BUILTIN_LEVELS == len(BUILTIN_NAMES)


def generate_needle(
    width: int = 25,
    height: int = 19,
    difficulty: float = 0.3,
    seed: int | None = None,
) -> str:
    """Generate a random single-screen needle level.

    A ground corridor with spike clusters and floating platforms. Constraints
    keep it human/agent-solvable with standard physics: spike runs <= 3 tiles
    (full jump covers ~4 tiles of horizontal distance), always a clean landing
    tile between hazards, goal on the far right.

    difficulty in [0, 1] scales spike density and run length.
    """
    rng = random.Random(seed)
    difficulty = max(0.0, min(1.0, difficulty))
    grid = [["." for _ in range(width)] for _ in range(height)]

    # walls + floor + ceiling
    for x in range(width):
        grid[0][x] = "#"
        grid[height - 1][x] = "#"
    for y in range(height):
        grid[y][0] = "#"
        grid[y][width - 1] = "#"

    floor_y = height - 2
    grid[floor_y][1] = "."
    grid[floor_y][1] = "S"
    grid[floor_y][width - 2] = "G"

    x = 3  # leave room after start
    max_run = 1 + round(2 * difficulty)          # 1..3 spikes in a row
    p_spike = 0.25 + 0.45 * difficulty           # cluster probability
    while x < width - 4:
        if rng.random() < p_spike:
            run = rng.randint(1, max_run)
            run = min(run, width - 4 - x)
            for i in range(run):
                grid[floor_y][x + i] = "^"
            # occasional floating platform above longer runs as an aid
            if run >= 2 and rng.random() < 0.5:
                py = floor_y - rng.randint(3, 4)
                px = x + rng.randint(0, run - 1)
                grid[py][px] = "#"
                # sometimes guard the platform with a ceiling spike
                if rng.random() < 0.3 * difficulty and py + 1 < floor_y:
                    grid[py + 1][px] = "v" if grid[py + 1][px] == "." else grid[py + 1][px]
            x += run + 2  # guaranteed >= 2 clean tiles after a cluster
        else:
            x += 1

    return "\n".join("".join(row) for row in grid) + "\n"
