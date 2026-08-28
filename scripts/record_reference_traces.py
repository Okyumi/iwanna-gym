"""Record the deterministic reference-trace fixtures used by
tests/test_exact_rooms.py::test_reference_trace_fixture and
tests/test_iwbtgr_bosses.py::test_birdo_reference_trace.

Run after an INTENTIONAL engine/pack behavior change, review the diff in
the trace hashes, and commit them. The traces pin the exact-layer
frame behavior (positions, deaths, rooms, boss state) under fixed
action scripts.
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


def record_rguy1():
    c = CIWanna.from_pack(G.load_pack(), seed=4242, checkpoint_respawn=True,
                          start_room=G.room_names().index("rGuy1"))
    c.reset()
    h = hashlib.sha256()
    for t in range(2000):
        c.step((t * 2654435761) % 12)
        h.update(f"{c.x:.4f},{c.y:.4f},{c.deaths},{c.room};".encode())
    c.close()
    return "iwbtgr_trace_rguy1.sha", h.hexdigest()


def record_birdo():
    """The scripted MechaBirdo kill (mirrors the test verbatim)."""
    names = G.room_names()
    room = names.index("rMechaBirdoBoss")
    c = CIWanna.from_pack(G.load_pack(), seed=3, checkpoint_respawn=True,
                          start_room=room, max_steps=200000)
    c.reset()
    h = hashlib.sha256()
    for t in range(1500):
        if c.room != room:
            h.update(b"EXIT")
            break
        b = c.bosses()
        a = 2
        if len(b):
            bx, by = float(b[0][10]), float(b[0][11])
            ph = int(b[0][1])
            if int(b[0][6]) & 2:                        # dead
                c.set_state(400, 300, 0, 0, 1)
            else:
                wy = {1: by - 700.0, 2: by - 600.0, 3: by - 570.0}[ph]
                c.set_state(bx - 300, wy, 0, 0, 1)
                a = 8 if t % 2 == 0 else 2
            h.update(f"{bx:.3f},{by:.3f},{ph},{b[0][3]:.1f};".encode())
        c.step(a)
        h.update(f"{c.x:.3f},{c.y:.3f};".encode())
    c.close()
    return "iwbtgr_trace_birdo.sha", h.hexdigest()


def main():
    for name, digest in (record_rguy1(), record_birdo()):
        out = os.path.join(FIX, name)
        with open(out, "w") as f:
            f.write(digest + "\n")
        print("wrote", out, digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
