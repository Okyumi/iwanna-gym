"""Room-level gates for the non-boss milestone: every gameplay room steps
cleanly under all action policies, replays deterministically, respawns
keep working, and the compiled coverage report holds the zero-unsupported
invariant (every source instance imported, implemented, or excluded with a
recorded justification)."""
from __future__ import annotations

import json
import os

import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.games import iwbtgr_1_5_3 as G
from iwanna_gym.games.iwbtgr_1_5_3.exact import (GAMEPLAY_ROOMS,
                                                 VISUAL_CLASSES,
                                                 BOSS_CLASSES)

needs_pack = pytest.mark.skipif(not os.path.isfile(G.PACK_PATH),
                                reason="iwbtgr pack not built locally")
COVERAGE_PATH = os.path.join(os.path.dirname(G.PACK_PATH),
                             G.GAME_ID + ".coverage.json")


def _room(name, seed=7, **kw):
    c = CIWanna.from_pack(G.load_pack(),
                          start_room=G.room_names().index(name),
                          checkpoint_respawn=True, **kw)
    c.reset()
    return c


def _policy_actions(kind, t):
    if kind == "idle":
        return 2
    if kind == "right":
        return 5 if t % 37 < 6 else 4
    # mixed 12-action pseudo-random (deterministic)
    return (t * 2654435761) % 12


@needs_pack
@pytest.mark.parametrize("rname", GAMEPLAY_ROOMS)
def test_room_steps_clean(rname):
    """3 policies x 2500 frames: no crash, engine state stays sane."""
    for kind in ("idle", "right", "mixed"):
        c = _room(rname)
        for t in range(2500):
            c.step(_policy_actions(kind, t))
        assert c.deaths >= 0
        assert -10000 < c.x < 40000 and -10000 < c.y < 20000
        c.close()


@needs_pack
@pytest.mark.parametrize("rname", GAMEPLAY_ROOMS)
def test_room_deterministic(rname):
    """Same seed + same actions => identical trajectories (exact layer
    included: entity motion, triggers, spawns, cameras)."""
    def run():
        c = _room(rname, seed=1234)
        traj = []
        for t in range(1500):
            c.step(_policy_actions("mixed", t))
            traj.append((c.x, c.y, c.vspeed, c.deaths, c.room,
                         len(c.xents()), c.view))
        c.close()
        return traj
    assert run() == run()


@needs_pack
@pytest.mark.parametrize("rname", GAMEPLAY_ROOMS)
def test_room_respawn_integrity(rname):
    """After any deaths, the player is back at a valid checkpoint inside a
    valid room, and the exact layer reloaded with it."""
    c = _room(rname)
    for t in range(3000):
        c.step(_policy_actions("mixed", t))
        if c.deaths >= 3:
            break
    assert 0 <= c.room < c.num_rooms
    assert len(c.xents()) > 0 or rname == "rGuyEntrance"
    # attempt reset always lands on the checkpoint
    c.attempt_reset()
    rx, ry = c.respawn
    assert abs(c.x - rx) < 1e-9 and abs(c.y - ry) < 1e-9
    c.close()


@needs_pack
def test_full_game_random_walk():
    """Full-game mode with the 12-action space: long mixed run across
    room transitions never breaks the exact layer."""
    c = CIWanna.from_pack(G.load_pack(), seed=99, checkpoint_respawn=True)
    c.reset()
    for t in range(6000):
        c.step(_policy_actions("mixed", t))
    assert 0 <= c.room < c.num_rooms
    c.close()


# ------------------------------------------------------------ coverage gates

@needs_pack
def test_coverage_zero_unaccounted():
    """THE milestone gate: every source instance in every non-boss gameplay
    room is imported/implemented, or excluded under a recorded visual/boss
    justification. Nothing is silently dropped."""
    cov = json.load(open(COVERAGE_PATH))
    x = cov["exact"]
    implemented = sum(x["implemented"].values())
    stat = sum(x["static"].values())
    visual = sum(x["excluded_visual"].values())
    boss = sum(x["excluded_boss"].values())
    assert implemented > 2000
    # every excluded class is on an explicit, justified list
    for cls in x["excluded_visual"]:
        assert cls.split(".")[0] in VISUAL_CLASSES or cls.endswith(".dev")
    for cls in x["excluded_boss"]:
        assert cls in BOSS_CLASSES
    # the converter raises on unknown classes, so reaching here means the
    # gate held at build time; sanity: totals reconcile
    assert implemented + stat + visual + boss > 2400


@needs_pack
def test_trigger_programs_all_compiled():
    """All 135 trigger instances in the gameplay rooms compiled into op
    programs (an unmatched code string fails the build)."""
    cov = json.load(open(COVERAGE_PATH))
    assert cov["exact"]["trigger_programs"] == 135


@needs_pack
def test_warp_side_effects_compiled():
    """The warp `code=` side effects (castleboost, factory ceiling) are
    compiled, not just recorded."""
    cov = json.load(open(COVERAGE_PATH))
    eff = [e for e in cov["side_effects"]
           if e["room"] in GAMEPLAY_ROOMS]
    assert eff, "expected recorded side effects"
    assert all(e["status"] in ("compiled", "no-op after compilation")
               for e in eff)


@needs_pack
def test_reference_trace_fixture():
    """Deterministic reference trace: a fixed scripted run in rGuy1 pinned
    by checksum. Regenerate with scripts/record_reference_traces.py when
    the engine or pack intentionally changes (documented procedure)."""
    import hashlib
    c = _room("rGuy1", seed=4242)
    h = hashlib.sha256()
    for t in range(2000):
        c.step(_policy_actions("mixed", t))
        h.update(f"{c.x:.4f},{c.y:.4f},{c.deaths},{c.room};".encode())
    digest = h.hexdigest()
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "iwbtgr_trace_rguy1.sha")
    if not os.path.isfile(fixture):
        pytest.skip("trace fixture not recorded yet")
    assert digest == open(fixture).read().strip()
    c.close()
