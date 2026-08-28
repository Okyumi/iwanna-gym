"""Record the deterministic reference-trace fixtures used by
tests/test_exact_rooms.py::test_reference_trace_fixture.

Run after an INTENTIONAL engine/pack behavior change, review the diff in
the trace hashes, and commit them. The traces pin the exact-layer
frame behavior (positions, deaths, rooms) under a fixed action script.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
from iwanna_gym.clib import CIWanna                      # noqa: E402
from iwanna_gym.games import iwbtgr_1_5_3 as G           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "tests", "fixtures")


def main():
    c = CIWanna.from_pack(G.load_pack(), seed=4242, checkpoint_respawn=True,
                          start_room=G.room_names().index("rGuy1"))
    c.reset()
    h = hashlib.sha256()
    for t in range(2000):
        c.step((t * 2654435761) % 12)
        h.update(f"{c.x:.4f},{c.y:.4f},{c.deaths},{c.room};".encode())
    c.close()
    out = os.path.join(FIX, "iwbtgr_trace_rguy1.sha")
    with open(out, "w") as f:
        f.write(h.hexdigest() + "\n")
    print("wrote", out, h.hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
