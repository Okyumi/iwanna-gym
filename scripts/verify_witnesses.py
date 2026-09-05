"""Replay-verify every committed discovery witness.

Usage: PYTHONPATH=. python scripts/verify_witnesses.py
Exit 0 iff every witness replays to task success. Native-task witnesses
need the local source-built pack (skipped with a notice otherwise).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")
import iwanna_gym.discovery as d                       # noqa: E402
from iwanna_gym.discovery import witness as W          # noqa: E402

PACK = "build/games/iwbtgr_1_5_3.iwpack"


def main() -> int:
    reg = d.load_registry()
    bad = skipped = ok = 0
    for spec in sorted(reg.values(), key=lambda t: t.task_id):
        if spec.witness_status != "witnessed":
            continue
        if spec.suite == "iwbtg_native" and not os.path.exists(PACK):
            skipped += 1
            continue
        w = d.load_witness(spec.task_id)
        good = W.verify_witness(spec, w)
        print(f"{spec.task_id:52s} {'OK' if good else 'FAIL'} "
              f"({w['frames']} frames, source={w['source']})")
        ok += good
        bad += (not good)
    print(f"\n{ok} verified, {bad} failed, {skipped} skipped (no pack)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
