"""Attempt reset vs task reset semantics (docs/action_and_reset_semantics.md)."""
from __future__ import annotations

import os

import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.games import iwbtgr_1_5_3 as G
from iwanna_gym.levels import load_level

needs_pack = pytest.mark.skipif(not os.path.isfile(G.PACK_PATH),
                                reason="iwbtgr pack not built locally")

N, R = 2, 4
SHOOT = 6


def _guy1():
    c = CIWanna.from_pack(G.load_pack(),
                          start_room=G.room_names().index("rGuy1"),
                          checkpoint_respawn=True)
    c.reset()
    return c


def _save_checkpoint(c):
    e = c.entities(4096)
    saves = e[e[:, 0] == 8]
    sx, sy = float(saves[0][1]), float(saves[0][2])
    c.set_state(sx, sy, 0, 0, 1)
    c.step(N + SHOOT)
    return c.respawn


@needs_pack
def test_attempt_reset_returns_to_checkpoint_without_death():
    c = _guy1()
    ckpt = _save_checkpoint(c)
    d0, a0 = c.deaths, c.attempt
    c.set_state(ckpt[0] + 200, ckpt[1] - 80, 0, 0, 1)
    c.attempt_reset()                      # source "R" quick-retry
    assert (c.x, c.y) == ckpt
    assert c.deaths == d0                  # no death counted
    assert c.attempt == a0 + 1
    assert c.vspeed == 0 and c.djump == 1
    c.close()


@needs_pack
def test_attempt_reset_fully_resets_room_state():
    """Pack retry = source room_goto: room objects recreated, bullets gone."""
    c = _guy1()
    _save_checkpoint(c)
    c.step(N)
    c.step(N + SHOOT)                      # a bullet is in flight
    e = c.entities()
    assert (e[:, 0] == 12).sum() >= 1
    c.attempt_reset()
    e = c.entities()
    assert (e[:, 0] == 12).sum() == 0      # bullet cleanup on retry
    c.close()


@needs_pack
def test_death_respawn_is_an_attempt_and_counts_death():
    import numpy as np
    c = _guy1()
    ckpt = _save_checkpoint(c)
    d0, a0 = c.deaths, c.attempt
    t = c.tiles()
    ys, xs = np.nonzero(t == 2)
    c.set_state(float(xs[0] * 32 + 16), float(ys[0] * 32 + 10), 0, 0, 1)
    c.step(N)
    assert c.deaths == d0 + 1
    assert c.attempt == a0 + 1
    assert (c.x, c.y) == ckpt
    c.close()


@needs_pack
def test_progression_flags_persist_across_attempts_not_tasks():
    c = _guy1()
    _save_checkpoint(c)
    flag = G.graph()["progression_flags"]["orb_dracula"]
    c.set_gflag(flag, True)
    c.attempt_reset()
    assert c.gflags >> flag & 1            # attempt keeps progression
    c.reset()                              # TASK reset
    assert c.gflags == 0                   # progression cleared
    assert c.attempt == 1
    assert c.deaths == 0
    c.close()


@needs_pack
def test_task_reset_clears_checkpoint_to_start():
    c = _guy1()
    start = (c.x, c.y)
    _save_checkpoint(c)
    assert c.respawn != start
    c.reset()
    c.attempt_reset()                      # attempt right after task reset
    assert (c.x, c.y) == start             # checkpoint is the room start
    c.close()


@needs_pack
def test_metadata_fields_exposed():
    import iwanna_gym as iw
    env = iw.IWannaEnv(game="iwbtgr_1_5_3", mode="room", room_id="rGuy1",
                       difficulty="hard", checkpoint_respawn=True)
    _, info = env.reset(seed=0)
    assert info["game_id"] == "iwbtgr_1_5_3"
    assert info["room_id"] == "rGuy1"
    assert info["attempt_id"] == 1
    assert info["death_count"] == 0
    assert info["difficulty"] == 1
    ck0 = info["checkpoint_id"]
    assert env.action_space.n == 12        # full space by default for games
    obs, info = env.attempt_reset()
    assert info["attempt_id"] == 2
    assert info["checkpoint_id"] == ck0
    env.close()


def test_classic_attempt_reset_keeps_room_state():
    """Classic single-room levels keep their historical semantics: attempt
    reset returns to the respawn point WITHOUT resetting entities/events
    (controlled trap-room experiments depend on it)."""
    c = CIWanna(load_level("traps/t03_riser"), seed=3, checkpoint_respawn=True)
    c.reset()
    spawn0 = c.entities().copy()
    for _ in range(120):                   # trip the room's trigger
        c.step(R)
    moved = c.entities()
    a0 = c.attempt
    c.attempt_reset()
    after = c.entities()
    assert c.attempt == a0 + 1
    # room state persists (no reset): entity snapshot unchanged by retry
    assert (after == moved).all()
    assert not (after.shape == spawn0.shape and (after == spawn0).all())
    c.close()


def test_classic_legacy_env_action_space_unchanged():
    import iwanna_gym as iw
    env = iw.IWannaEnv(level="gaps")
    assert env.action_space.n == 6         # legacy default preserved
    env.close()
    env = iw.IWannaEnv(level="gaps", action_mode="full")
    assert env.action_space.n == 12
    env.close()
