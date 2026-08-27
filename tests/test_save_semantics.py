"""Source-faithful save semantics (IWBTGR: shot-activated saves storing
the player's exact position/facing; 50-frame saveTimer; difficulty
gating). Pack-backed tests skip when the local iwbtgr pack is not built."""
from __future__ import annotations

import os

import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.games import iwbtgr_1_5_3 as G
from iwanna_gym.levels import load_level

needs_pack = pytest.mark.skipif(not os.path.isfile(G.PACK_PATH),
                                reason="iwbtgr pack not built locally")

N, R, L = 2, 4, 0
SHOOT = 6


def _guy1(**kw):
    c = CIWanna.from_pack(G.load_pack(),
                          start_room=G.room_names().index("rGuy1"),
                          checkpoint_respawn=True, **kw)
    c.reset()
    return c


def _first_save(c):
    e = c.entities(4096)
    saves = e[e[:, 0] == 8]
    return float(saves[0][1]), float(saves[0][2])


# ------------------------------------------------------------- shot saves

@needs_pack
def test_pack_default_is_shoot_mode():
    c = _guy1()
    assert c.save_shoot_mode is True
    c.close()


def _shooting_spot(c, min_cols=3, max_cols=8):
    """Find (save_x, save_y, player_x, player_y, dir) with a tile-clear
    bullet corridor between the player and some save, from the live grid."""
    t = c.tiles()
    e = c.entities(4096)
    for s in e[e[:, 0] == 8]:
        sx, sy = float(s[1]), float(s[2])
        trow, scol = int(sy) // 32, int(sx) // 32
        for side in (+1, -1):              # stand right of the save, or left
            for d in range(min_cols, max_cols + 1):
                col = scol + side * d
                if not (1 <= col < t.shape[1] - 1):
                    break
                lo, hi = (scol + 1, col) if side > 0 else (col, scol - 1)
                if t[trow - 1][col] == 0 and t[trow][col] == 0 and \
                        all(t[trow][k] == 0 for k in range(lo, hi + 1)):
                    return sx, sy, col * 32 + 16.0, sy, -side
    raise AssertionError("no clear shooting corridor found near any save")


@needs_pack
def test_bullet_activates_save_at_distance():
    c = _guy1()
    sx, sy, px, py, face = _shooting_spot(c)
    c.set_state(px, py, 0, 0, 1)
    c.step(R if face > 0 else L)           # face toward the save
    c.set_state(px, py, 0, 0, 1)
    r0 = c.respawn
    c.step(N + SHOOT)                      # fire
    hit = False
    for _ in range(16):
        c.step(N)
        if c.respawn != r0:
            hit = True
            break
    assert hit, "bullet never reached the save"
    # checkpoint = the PLAYER's position in the frame the bullet HIT (GM
    # runs bullet collision events after movement; saveGame stores savex/y)
    rx, ry = c.respawn
    assert (rx, ry) == (c.x, c.y)
    assert abs(rx - px) < 1e-9             # shooter stayed put (idle)
    c.close()


@needs_pack
def test_shoot_while_overlapping_save_contact_path():
    c = _guy1()
    sx, sy = _first_save(c)
    c.set_state(sx, sy, 0, 0, 1)
    r0 = c.respawn
    c.step(N + SHOOT)
    assert c.respawn != r0
    # saved position = the player's exact position AT THE SHOT (pre-move,
    # player Step order), i.e. where set_state placed it
    assert c.respawn == (sx, sy)
    c.close()


@needs_pack
def test_save_timer_50_frame_cooldown():
    c = _guy1()
    sx, sy = _first_save(c)
    c.set_state(sx, sy, 0, 0, 1)
    c.step(N + SHOOT)                      # activate (frame 0 of cooldown)
    first = c.respawn
    c.set_state(sx + 9, sy, 0, 0, 1)       # different spot on the save
    c.step(N)                              # release
    c.step(N + SHOOT)                      # within saveTimer: ignored
    assert c.respawn == first
    for _ in range(50):                    # cooldown expires
        c.step(N)
    c.set_state(sx + 9, sy, 0, 0, 1)
    c.step(N + SHOOT)
    assert c.respawn != first
    c.close()


@needs_pack
def test_touch_does_not_save_in_shoot_mode():
    c = _guy1()
    sx, sy = _first_save(c)
    r0 = c.respawn
    c.set_state(sx, sy, 0, 0, 1)
    for _ in range(10):
        c.step(N)                          # stand on the save, no shooting
    assert c.respawn == r0
    c.close()


@needs_pack
def test_touch_mode_remains_available_as_research_option():
    c = _guy1()
    c.set_save_mode(False)                 # legacy touch mode
    sx, sy = _first_save(c)
    r0 = c.respawn
    c.set_state(sx, sy, 0, 0, 1)
    c.step(N)
    assert c.respawn != r0                 # touched save saved
    c.close()


@needs_pack
def test_facing_stored_and_restored():
    """savew: facing is saved with the checkpoint and restored on retry —
    a bullet fired right after respawn flies in the SAVED direction."""
    c = _guy1()
    sx, sy = _first_save(c)
    c.set_state(sx, sy, 0, 0, 1)
    c.step(L)                              # face left
    c.set_state(sx, sy, 0, 0, 1)
    c.step(N + SHOOT)                      # save while facing left
    assert c.respawn_face == -1
    c.attempt_reset()                      # retry restores facing
    c.step(N)                              # settle frame (no h input)
    c.step(N + SHOOT)                      # release wasn't needed: new press
    e = c.entities()
    b = e[e[:, 0] == 12]
    assert len(b) >= 1 and b[-1][3] == -16.0   # fired LEFT
    c.close()


# ------------------------------------------------- difficulty + persistence

@needs_pack
def test_difficulty_gated_saves_shootable():
    g = G.graph()
    r = next(rr for rr in g["rooms"] if rr["name"] == "rGuy1")
    for diff, dname in ((0, "medium"), (2, "very_hard")):
        c = CIWanna.from_pack(G.load_pack(),
                              start_room=G.room_names().index("rGuy1"),
                              difficulty=diff, checkpoint_respawn=True)
        c.reset()
        e = c.entities(4096)
        assert int((e[:, 0] == 8).sum()) == r["saves_by_difficulty"][dname]
        c.close()


@needs_pack
def test_checkpoint_persists_across_room_transition_and_death():
    names = G.room_names()
    c = _guy1()
    sx, sy = _first_save(c)
    c.set_state(sx, sy, 0, 0, 1)
    c.step(N + SHOOT)                      # checkpoint in rGuy1
    ckpt = c.respawn
    ckpt_room = c.respawn_room
    # warp to rZelda through the right-edge warp
    c.set_state(4796, 1232, 0, 0, 1)
    while c.room == names.index("rGuy1"):
        c.step(R)
    assert names[c.room] == "rZelda"
    assert c.respawn == ckpt and c.respawn_room == ckpt_room
    # die in rZelda -> respawn at the rGuy1 checkpoint, room reset
    d0 = c.deaths
    import numpy as np
    t = c.tiles()
    ys, xs = np.nonzero((t >= 2) & (t <= 5))   # spike tiles...
    if len(xs):
        kx, ky = float(xs[0] * 32 + 16), float(ys[0] * 32 + 16)
    else:                                       # ...or killer shapes (rZelda)
        k = c.killers()[0]
        kx, ky = float((k[1] + k[3]) / 2), float((k[2] + k[4]) / 2)
    c.set_state(kx, ky, 0, 0, 1)
    c.step(N)
    assert c.deaths == d0 + 1
    assert names[c.room] == "rGuy1"
    assert (c.x, c.y) == ckpt
    c.close()


def test_classic_touch_saves_unchanged():
    """Legacy touch semantics in classic levels: respawn at the SAVE's
    position (historical behavior for research rooms)."""
    lvl = load_level("traps/t09_fakesave")
    c = CIWanna(lvl, seed=3, checkpoint_respawn=True)
    c.reset()
    assert c.save_shoot_mode is False
    c.close()
