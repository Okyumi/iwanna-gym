"""Generate the informative-failure controlled rooms (levels/informative/).

Each room is a flat corridor from S (left) to G (right). At a hidden tile
column ``Xt`` an INVISIBLE ``enter_region`` band at floor level spawns a
lethal spike ON a grounded player. The band and the spike do not exist in
the observation until the spike is spawned (offscreen/unspawned entities are
excluded from the observable vector), so the trap column is NOT derivable
from the observation on the first attempt — it is *initially ambiguous
hidden state*. The only way to learn Xt is to die there (an OBSERVABLE
failure: the agent's own last position before it died reveals Xt). A player
that is AIRBORNE over the band (jumped before Xt, lands after) never enters
the region, so the spike never spawns — the failure information (where the
trap is) is exactly what lets a later attempt succeed.

Xt VARIES across the configs, so no single fixed action sequence (e.g.
"always jump at tile 10") clears more than the few configs whose trap
happens to sit there — defeating solve-by-memorization. Hidden state is a
CONFIG parameter, not an RNG seed: the rooms are fully deterministic, so
"3 seeds" would be one configuration run three times; distinct rooms are
distinct configurations.

Emits one .txt per config plus manifest rows for
manifests/discovery_task_candidates.toml (added by the caller).
"""
from __future__ import annotations

import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "iwanna_gym", "levels", "informative")

W, H = 25, 19
FLOOR_ROW = 17            # walkable row (solid row 18 below)
# hidden trap columns — spread across the corridor so a fixed jump x clears
# at most one of them
TRAP_COLS = [6, 8, 10, 12, 14, 16, 18]


def base_rows():
    rows = ["#" * W]
    for _ in range(1, FLOOR_ROW):
        rows.append("#" + "." * (W - 2) + "#")
    rows.append("#S" + "." * (W - 4) + "G#")
    rows.append("#" * W)
    return rows


def room_text(xt: int) -> str:
    rows = base_rows()
    tiles = "\n".join(rows)
    # invisible floor-level band at [xt, xt+1] x [16,19] tiles: a grounded
    # player overlaps it; an airborne player (above row 16) does not. On
    # entry, spawn a deadly spike on the floor at the trap column.
    events = (
        f"!when=enter_region x0={xt} y0=16 x1={xt + 1} y1=19 "
        f"-> spawn type=spikeball x={xt} y={FLOOR_ROW} deadly=1\n"
    )
    return tiles + "\n" + events


def main():
    os.makedirs(OUT, exist_ok=True)
    for i, xt in enumerate(TRAP_COLS):
        name = f"hidden_spike_{i}"
        with open(os.path.join(OUT, name + ".txt"), "w") as f:
            f.write(room_text(xt))
        print(f"wrote {name}.txt  trap_col={xt}")
    print(f"{len(TRAP_COLS)} informative-failure rooms in {OUT}")


if __name__ == "__main__":
    main()
