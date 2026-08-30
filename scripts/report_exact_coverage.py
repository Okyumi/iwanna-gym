"""Render the machine-written coverage JSON of an exact game build into the
human-readable coverage report (docs/iwbtgr_nonboss_coverage.md).

The JSON is produced by `python -m iwanna_gym.games.iwbtgr_1_5_3` (build);
this script only formats it, so the doc can never drift from the build
without showing up in review:

    python scripts/report_exact_coverage.py
"""
from __future__ import annotations

import json
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
from iwanna_gym.games import iwbtgr_1_5_3 as G                # noqa: E402
from iwanna_gym.games.iwbtgr_1_5_3 import exact as X          # noqa: E402

COVERAGE_PATH = os.path.join(os.path.dirname(G.PACK_PATH),
                             G.GAME_ID + ".coverage.json")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "docs", "iwbtgr_nonboss_coverage.md")


def table(rows, headers):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def main():
    cov = json.load(open(COVERAGE_PATH))
    x = cov["exact"]
    impl, stat = x["implemented"], x["static"]
    vis, boss = x["excluded_visual"], x["excluded_boss"]

    L = []
    L.append("# IWBTGR 1.5.3 non-boss coverage report")
    L.append("")
    L.append("Generated from `build/games/%s.coverage.json` by"
             % G.GAME_ID)
    L.append("`scripts/report_exact_coverage.py`. The numbers are written by "
             "the converter at build time; an instance that matches no row "
             "here fails the build (`ConversionError`), so this table is the "
             "complete account of every placed instance in the %d gameplay "
             "rooms." % len(X.GAMEPLAY_ROOMS))
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append(table([
        ("implemented (dynamic exact-layer entities)",
         len(impl), sum(impl.values())),
        ("static geometry (lowered to solids/killers at build time)",
         len(stat), sum(stat.values())),
        ("excluded — visual/decorative only", len(vis), sum(vis.values())),
        ("excluded — boss fight content (out of milestone scope)",
         len(boss), sum(boss.values())),
        ("trigger op-programs compiled", "—", x["trigger_programs"]),
    ], ("category", "classes", "instances")))
    L.append("")
    L.append("Gameplay rooms: " + ", ".join(f"`{r}`"
                                            for r in X.GAMEPLAY_ROOMS) + ".")
    L.append("")

    L.append("## Implemented classes")
    L.append("")
    L.append("Every source object lowered to a dynamic exact-layer entity, "
             "with its placed-instance count across the gameplay rooms. "
             "Per-class source semantics (constants, timings, state "
             "machines, and which native behavior class each object lowers "
             "to) are documented in `docs/iwbtgr_nonboss_mechanics.md`.")
    L.append("")
    objs = sorted(impl.items(), key=lambda kv: (-kv[1], kv[0]))
    ncol, rows = 3, []
    nrow = (len(objs) + ncol - 1) // ncol
    for i in range(nrow):
        cells = []
        for j in range(ncol):
            k = j * nrow + i
            cells += ([f"`{objs[k][0]}`", objs[k][1]] if k < len(objs)
                      else ["", ""])
        rows.append(cells)
    L.append(table(rows, ("object", "n", "object", "n", "object", "n")))
    L.append("")

    L.append("## Static-only classes")
    L.append("")
    L.append("Objects whose source events reduce to immobile solid "
             "geometry (`solid=1`, no gameplay code beyond being stood on); "
             "the converter rasterizes their sprite masks into the static "
             "collision layers at build time.")
    L.append("")
    L.append(table(sorted(stat.items(), key=lambda kv: -kv[1]),
                   ("object", "instances")))
    L.append("")

    L.append("## Excluded: visual/decorative")
    L.append("")
    L.append("Classes whose source events contain no gameplay-relevant code "
             "(draw/animation/depth only), plus `JumpRefresher`, which the "
             "source destroys at create unless a non-default character is "
             "selected. The allowlist lives in `exact.VISUAL_CLASSES`; an "
             "object not on it cannot be excluded this way.")
    L.append("")
    L.append(table(sorted(vis.items(), key=lambda kv: -kv[1]),
                   ("object", "instances")))
    L.append("")

    L.append("## Excluded: boss content")
    L.append("")
    L.append("Since the full-game milestone every boss is implemented, so "
             "this bucket is empty; it remains a build gate — any placed "
             "boss-class instance that loses its implementation lands "
             "here and fails coverage. See "
             "[iwbtgr_boss_coverage.md](iwbtgr_boss_coverage.md) for the "
             "boss catalogue.")
    L.append("")
    L.append(table(sorted(boss.items(), key=lambda kv: -kv[1]),
                   ("object", "instances")))
    L.append("")

    L.append("## Trigger programs targeting excluded classes")
    L.append("")
    L.append("Trigger instances whose op programs reference boss/cosmetic "
             "targets compile with a recorded note (the pulse becomes a "
             "no-op at runtime until the target class exists):")
    L.append("")
    for room, notes in x["boss_exception_notes"].items():
        for n in notes:
            L.append(f"- `{room}`: {n}")
    L.append("")

    t = cov["totals"]
    L.append("## Whole-source reconciliation")
    L.append("")
    L.append("Across the entire source project (boss rooms, menus, cutscene "
             "rooms included): %d placed instances, %d imported, %d "
             "excluded with recorded reasons (`excluded_reasons` in the "
             "JSON). Within the %d non-boss gameplay rooms the account "
             "above is exhaustive: %d implemented + %d static + %d visual + "
             "%d boss-content = every instance."
             % (t["instances_in_source"], t["instances_imported"],
                t["instances_excluded"], len(X.GAMEPLAY_ROOMS),
                sum(impl.values()), sum(stat.values()), sum(vis.values()),
                sum(boss.values())))
    L.append("")

    with open(OUT, "w") as f:
        f.write("\n".join(L))
    print("wrote", os.path.normpath(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
