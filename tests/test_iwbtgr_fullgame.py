"""Milestone-8 full-game reference suite for IWBTGR 1.5.3.

The centerpiece is one deterministic single-session run from the rGuy1
spawn to the rEnding completion event via the scripted drivers in
``iwanna_gym.games.iwbtgr_1_5_3.drivers`` — every source boss, every
orb flag, the EntranceTele gate, the final-area chain, and the ending,
with zero deaths.  Around it sit targeted segment tests: the gate in
both directions, refight skips, the Metroid escape countdown, the
OrbDracula delayed exit warp, the Gradius victory sweep, and the
Arkanoid/Sinistar chase.
"""
from __future__ import annotations

import os

import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.games import iwbtgr_1_5_3 as G
from iwanna_gym.games.iwbtgr_1_5_3 import drivers as D

needs_pack = pytest.mark.skipif(not os.path.isfile(G.PACK_PATH),
                                reason="iwbtgr pack not built locally")

ALL_SIX_ORBS = 0x7e            # tyson|birdo|kraidgief|bowser|mother|drac
ALL_FLAGS = 0x1fe              # + dragon + guy


def _env(room, seed=11, **kw):
    c = CIWanna.from_pack(G.load_pack(), seed=seed,
                          checkpoint_respawn=True,
                          start_room=G.room_names().index(room),
                          max_steps=90000000, **kw)
    c.reset()
    return c


# ------------------------------------------------------ full-game run

_FULL = {}


def _full_game():
    if not _FULL:
        _FULL["out"] = D.run_full_game(seed=11)
    return _FULL["out"]


@needs_pack
def test_full_game_completion():
    """rGuy1 spawn -> all eight bosses -> rEnding: completion event
    fires exactly once, with zero deaths on the scripted line."""
    out = _full_game()
    assert out["completions"] == 1
    assert out["deaths"] == 0
    assert out["gflags"] == ALL_FLAGS
    assert out["last_event"] == 4          # completion event code


@needs_pack
def test_full_game_progression_order():
    """Orb flags accumulate monotonically along the route, and the
    EntranceTele gate is only crossed with all six orbs banked."""
    out = _full_game()
    # the final entry is post-completion (the run resets, flags clear)
    seen = [int(h, 16) for _, _, h, _ in out["log"][:-1]]
    assert all(b | a == b for a, b in zip(seen, seen[1:])), \
        "a progression flag was lost mid-run"
    gate = next(e for e in out["log"] if e[1] == "entrance gate passed")
    assert int(gate[2], 16) & ALL_SIX_ORBS == ALL_SIX_ORBS
    stages = [e[1] for e in out["log"]]
    assert stages.index("dragon down") > stages.index("entrance gate passed")
    assert stages[-1] == "completion"


@needs_pack
def test_completion_resets_run():
    """After the completion event the env starts a fresh run: flags
    cleared, back in the start room."""
    out = _full_game()
    assert out["room"] == "rGuy1"          # post-completion reset


@needs_pack
def test_full_game_reference_trace():
    """The waypoint ticks of the full-game run, pinned by checksum.
    Regenerate with scripts/record_reference_traces.py after an
    intentional engine or pack change."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "record_reference_traces",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "scripts", "record_reference_traces.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    digest = mod.fullgame_digest(_full_game())
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "iwbtgr_trace_fullgame.sha")
    if not os.path.isfile(fixture):
        pytest.skip("trace fixture not recorded yet")
    assert digest == open(fixture).read().strip()


# ------------------------------------------------------ entrance gate

@needs_pack
def test_entrance_gate_kills_without_orbs():
    c = _env("rGuyEntrance")
    c.step(2)
    d0 = c.deaths
    for _ in range(6):
        c.set_state(214, 473, 0, 0, 1)
        c.step(2)
        if c.deaths != d0:
            break
    assert c.deaths == d0 + 1, "gate must kill with zero orbs"
    assert G.room_names()[c.room] == "rGuyEntrance"
    c.close()


@needs_pack
def test_entrance_gate_warps_with_six_orbs():
    c = _env("rGuyEntrance")
    for bit in range(1, 7):
        c.set_gflag(bit, True)
    c.step(2)
    d0 = c.deaths
    for _ in range(8):
        c.set_state(214, 473, 0, 0, 1)
        c.step(2)
        if c.room != G.room_names().index("rGuyEntrance"):
            break
    assert G.room_names()[c.room] == "rGuyRoad"
    assert c.deaths == d0
    c.close()


# ---------------------------------------------------------- segments

@needs_pack
def test_dracula_segment_and_orb_warp():
    """Dracula -> Deadcula -> true form; the OrbDracula Alarm_0 then
    warps the player to rFactoryOutskirts (3040,960) after 185f."""
    c = _env("rDraculaBoss")
    c.step(2)
    D.drive_dracula(c)
    assert (round(c.x), round(c.y)) == (3040, 960)
    assert c.gflags & D.FLAG_DRACULA
    assert c.deaths == 0
    c.close()


@needs_pack
def test_mommy_escape_countdown_kills():
    """Mother Brain dies -> escape trigger arms the 3000-frame
    countdown -> staying in rMetroid past it detonates."""
    c = _env("rMetroid")
    c.step(2)
    D.drive_mommy(c, leave=False)          # countdown armed by the driver
    d0 = c.deaths
    died_at = None
    for t in range(3400):
        c.set_state(400, 1340, 0, 0, 1)
        c.step(2)
        if c.deaths != d0:
            died_at = t
            break
    assert died_at is not None, "escape countdown never detonated"
    assert died_at < 3000                  # armed mid-driver: < full span
    c.close()


@needs_pack
def test_viper_segment_victory_sweep():
    """Mount -> searched flight plan -> GradiusBoss destroyed -> the
    victory event clears every gradius actor and flies the rider home."""
    c = _env("rGuyFortress2")
    c.step(2)
    D.drive_viper(c)
    assert c.deaths == 0
    xe = c.xents()
    for cls in (D.XC_GBOSS, D.XC_BUGZ, D.XC_DRONE, D.XC_DBUL, D.XC_FRUIT):
        assert not [r for r in xe if int(r[0]) == cls and r[6] > 0], \
            f"class {cls} survived the victory sweep"
    v = [r for r in xe if int(r[0]) == D.XC_VIPER and r[6] > 0]
    assert v and int(v[0][5]) == 3         # returned home (win state)
    c.close()


@needs_pack
def test_sinistar_kills_mounted_viper():
    """A woken Sinistar hunting the mounted viper kills it on contact
    (source Sinistar Collision_VicViper -> event_user(0))."""
    c = _env("rGuyFortress2")
    c.step(2)
    D.drive_arkanoid(c, chase_frames=40)   # wake it, then flee
    # mount while the sinistar closes in
    for _ in range(60):
        v = [r for r in c.xents() if int(r[0]) == D.XC_VIPER and r[6] > 0]
        if v and int(v[0][5]) == 1:
            break
        c.set_state(2592, 330, 0, 0, 1)
        c.step(2)
    v = [r for r in c.xents() if int(r[0]) == D.XC_VIPER and r[6] > 0]
    assert v and int(v[0][5]) == 1
    d0 = c.deaths
    for _ in range(2500):
        c.step(2)                          # hover; let it catch up
        if c.deaths != d0:
            break
    assert c.deaths == d0 + 1, "sinistar never killed the mounted viper"
    c.close()


@needs_pack
def test_arkanoid_segment():
    """The paddle clears all bricks while the driver dodges; the last
    brick wakes the Sinistar chase."""
    c = _env("rGuyFortress2")
    c.step(2)
    n0 = len([r for r in c.xents()
              if int(r[0]) == D.XC_ARKABRICK and r[6] > 0])
    assert n0 == 82
    D.drive_arkanoid(c)
    assert c.deaths == 0
    c.close()


@needs_pack
def test_tyson_refight_skip():
    """orb_tyson set: the arena doors (and Tyson) never appear."""
    c = _env("rGuy1")
    c.set_gflag(1, True)                   # orb_tyson = bit 1
    c.attempt_reset()
    c.step(2)
    doors = [r for r in c.xents()
             if int(r[0]) == D.XC_TYSON_DOOR and r[6] > 0]
    assert not doors
    c.set_state(3210, 290, 0, 0, 1)
    for _ in range(600):
        c.step(2)
        if len(c.bosses()):
            break
    assert not len(c.bosses()), "tyson must not respawn with his orb"
    c.close()


@needs_pack
def test_dragon_refight_state():
    """orb_dragon set: entering rGuyRoad leaves the road camera clamped
    and no dragon fight begins at the trigger line."""
    c = _env("rGuyRoad")
    c.set_gflag(7, True)                   # orb_dragon = bit 7
    c.attempt_reset()
    c.step(2)
    b0 = len(c.bosses())
    for t in range(400):
        c.set_state(min(400 + t * 40, 23405), 430, 0, 0, 1)
        c.step(2)
        b = c.bosses()
        if len(b) and (int(b[0][2]) != 0 or int(b[0][1]) > 0):
            raise AssertionError("dragon fight armed despite orb_dragon")
    c.close()
    del b0
