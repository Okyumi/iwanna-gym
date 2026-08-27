"""Tests for the trigger/event system (conditions, actions, trap rooms)."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from iwanna_gym.env import IWannaEnv          # noqa: E402
from iwanna_gym.levels import list_levels     # noqa: E402

TILE = 32
BLANK = ["#" + "." * 23 + "#" for _ in range(16)]
FLOOR = ["#S" + "." * 21 + "G#", "#" * 25]
TOP = ["#" * 25]


def room(*extra):
    return "\n".join(TOP + BLANK + FLOOR + list(extra)) + "\n"


def env_of(*extra, **kw):
    kw.setdefault("max_steps", 2000)
    e = IWannaEnv(level=room(*extra), death_penalty=1.0, **kw)
    e.reset(seed=0)
    return e


def run(e, action, n):
    term = trunc = False
    for _ in range(n):
        _, _, term, trunc, _ = e.step(action)
        if term or trunc:
            break
    return term or trunc


# ---------- condition primitives ----------

def test_pass_x_fires_on_crossing():
    e = env_of("@fruit 20 5 tag=9",
               "!when=pass_x x=6 dir=right -> launch tag=9 vy=3")
    while e.c.x < 6 * TILE - 6:
        e.step(4)
        assert e.c.entities()[0][4] == 0.0    # not yet
    for _ in range(4):
        e.step(4)
    assert e.c.entities()[0][4] == 3.0        # fired at crossing


def test_pass_x_direction_filter():
    e = env_of("@fruit 20 5 tag=9",
               "!when=pass_x x=3 dir=left -> launch tag=9 vy=3")
    run(e, 4, 60)                              # cross rightward: no fire
    assert e.c.entities()[0][4] == 0.0
    run(e, 0, 80)                              # come back leftward: fires
    assert e.c.entities()[0][4] == 3.0


def test_enter_and_leave_region():
    e = env_of("@fruit 20 5 tag=1", "@fruit 22 5 tag=2",
               "!when=enter_region x0=5 y0=0 x1=7 y1=19 -> launch tag=1 vy=2",
               "!when=leave_region x0=0 y0=0 x1=4 y1=19 -> launch tag=2 vy=2")
    run(e, 4, 40)                              # leave start region first
    ents = {r[1]: r for r in e.c.entities()}
    assert ents[22 * TILE + 16][4] == 2.0
    run(e, 4, 40)                              # then enter mid region
    ents = {r[1]: r for r in e.c.entities()}
    assert ents[20 * TILE + 16][4] == 2.0


def test_touch_and_land():
    e = env_of("@platform 6 15 tag=3", "@fruit 20 5 tag=8",
               "!when=land tag=3 -> launch tag=8 vy=1")
    run(e, 4, 30)
    for _ in range(26):
        e.step(5)                              # jump onto platform
    for _ in range(40):
        e.step(4 if e.c.obs[5] < 0.5 else 2)
    assert e.c.entities()[1][4] == 1.0


def test_timer_period_spawns():
    e = env_of("!when=timer delay=20 period=30 -> "
               "spawn type=bullet x=22 y=5 vx=-1")
    counts = []
    for _ in range(100):
        e.step(2)
        counts.append(len(e.c.entities()))
    assert counts[15] == 0
    assert counts[25] == 1
    assert counts[55] == 2
    assert counts[85] == 3


def test_destroyed_and_save_chain():
    e = env_of("@save 5 17 tag=7", "@fruit 20 5 tag=6",
               "@fruit 22 5 tag=5",
               "!when=save tag=7 -> destroy tag=6",
               "!when=destroyed tag=6 -> launch tag=5 vy=2")
    run(e, 4, 60)
    ents = [r for r in e.c.entities() if r[0] == 2]
    live = [r for r in ents if r[1] == 22 * TILE + 16]
    assert live and live[0][4] == 2.0


def test_room_enter_delay():
    e = env_of("@fruit 20 5 tag=4",
               "!when=room_enter delay=25 -> launch tag=4 vy=1")
    run(e, 2, 20)
    assert e.c.entities()[0][4] == 0.0
    run(e, 2, 10)
    assert e.c.entities()[0][4] == 1.0


# ---------- action primitives ----------

def test_gate_blocks_then_opens():
    e = env_of("@gate 12 14 w=1 h=4 tag=2",
               "!when=pass_x x=8 dir=right delay=60 -> open_gate tag=2")
    run(e, 4, 120)
    assert e.c.x < 12 * TILE                   # blocked while closed
    ok = run(e, 4, 300)
    assert ok and e.c.last_event == 2          # opened, reached goal


def test_close_gate_behind():
    e = env_of("@gate 5 14 w=1 h=4 tag=2 open=1",
               "!when=pass_x x=7 dir=right -> close_gate tag=2")
    run(e, 4, 80)
    x_after = e.c.x
    run(e, 0, 200)                             # try to walk back
    assert e.c.x > 5 * TILE                    # gate closed behind
    assert x_after > 7 * TILE


def test_move_and_set_gravity():
    e = env_of("@fruit 20 5 tag=3",
               "!when=room_enter -> move tag=3 dy=64 ; "
               "set_gravity tag=3 grav=0.5")
    e.step(2)
    r0 = e.c.entities()[0]
    assert r0[2] == 5 * TILE + 16 + 64
    run(e, 2, 10)
    assert e.c.entities()[0][4] > 0            # falling


def test_teleport_player():
    e = env_of("!when=pass_x x=6 dir=right -> teleport tag=-1 gx=18 gy=16")
    run(e, 4, 80)
    assert e.c.x > 17 * TILE                   # jumped ahead


def test_spawn_is_deadly_by_default():
    e = env_of("!when=room_enter -> spawn type=fruit x=3 y=17 vx=0")
    dead = run(e, 4, 60)
    assert dead and e.c.last_event == 1


def test_make_killer_and_harmless():
    e = env_of("@platform 6 15 tag=3",
               "!when=room_enter -> make_killer tag=3",
               "!when=pass_x x=4 dir=right -> make_harmless tag=3")
    run(e, 4, 200)
    assert e.c.last_event != 1                 # harmless before contact


def test_activate_deactivate():
    e = env_of("@fruit 8 17 tag=5 active=0",
               "!when=pass_x x=5 dir=right -> activate tag=5")
    e.step(2)
    assert len(e.c.entities()) == 0            # inactive: not exported
    dead = run(e, 4, 120)
    assert dead and e.c.last_event == 1        # activated in the path


def test_start_timer_chain():
    e = env_of("@fruit 20 5 tag=6",
               "!when=pass_x x=5 dir=right -> start_timer id=9",
               "!when=timer id=9 auto=0 delay=30 -> launch tag=6 vy=2")
    run(e, 4, 50)                              # crossing arms the timer
    assert e.c.entities()[0][4] == 0.0
    run(e, 2, 35)
    assert e.c.entities()[0][4] == 2.0


# ---------- trap rooms ----------

TRAPS = [n for n in list_levels() if n.startswith("traps/")]


def test_twenty_trap_rooms_exist():
    assert len(TRAPS) == 20


@pytest.mark.parametrize("name", TRAPS)
def test_trap_room_loads_and_steps(name):
    e = IWannaEnv(level=name, max_steps=200)
    obs, _ = e.reset(seed=0)
    assert obs.shape == (101,)
    for _ in range(100):
        obs, r, term, trunc, info = e.step(4)
        if term or trunc:
            break
    assert np.isfinite(obs).all()


def test_all_trap_rooms_solvable_by_scripted_probe():
    import probe_traps
    fails = []
    for room_name, fn in sorted(probe_traps.PROBES.items()):
        ok, t, ev, _, _ = probe_traps.run_probe(room_name, fn)
        if not ok:
            fails.append((room_name, ev, t))
    assert not fails, f"unsolved rooms: {fails}"


def test_signature_room_punishes_sprinting():
    e = IWannaEnv(level="traps/t01_apple", max_steps=600, death_penalty=1.0)
    e.reset(seed=0)
    dead = run(e, 4, 600)
    assert dead and e.c.last_event == 1        # apple lands on the runner


def test_deterministic_replay_event_room():
    import probe_traps
    ok, _, _, acts, _ = probe_traps.run_probe(
        "t20_finale", probe_traps.PROBES["t20_finale"])
    assert ok
    trajs = []
    for _ in range(2):
        e = IWannaEnv(level="traps/t20_finale", max_steps=3000,
                      death_penalty=1.0)
        e.reset(seed=0)
        tr = []
        for a in acts:
            obs, r, term, trunc, info = e.step(a)
            tr.append((obs.copy(), r, term, trunc))
            if term or trunc:
                break
        trajs.append(tr)
    assert len(trajs[0]) == len(trajs[1])
    for (o1, r1, t1, u1), (o2, r2, t2, u2) in zip(*trajs):
        assert np.array_equal(o1, o2) and r1 == r2 and t1 == t2 and u1 == u2
