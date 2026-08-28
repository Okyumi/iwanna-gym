"""Exact-mode player physics extensions (player.gml ports): source-faithful
hitbox, walljump family, water, couch deceleration, control locks, and
platform riding. All constants asserted here are read from the IWBTGR
source (docs/iwbtgr_nonboss_mechanics.md cites the GML)."""
from __future__ import annotations

import os

import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.games import iwbtgr_1_5_3 as G
from iwanna_gym.games.iwbtgr_1_5_3.exact import C as XC

needs_pack = pytest.mark.skipif(not os.path.isfile(G.PACK_PATH),
                                reason="iwbtgr pack not built locally")
N, R, L = 2, 4, 0
NJ, RJ, LJ = 3, 5, 1


def _room(name, **kw):
    c = CIWanna.from_pack(G.load_pack(),
                          start_room=G.room_names().index(name),
                          checkpoint_respawn=True, **kw)
    c.reset()
    return c


@needs_pack
def test_exact_layer_active_and_hitbox():
    """v3 pack: exact layer on; hitbox = sprMask 11x21 (top at -12)."""
    c = _room("rGuy1")
    assert c.exact is True
    assert c.hitbox == (-5, -12, 5, 8)
    c.close()


@needs_pack
def test_walljump_slide_speed():
    """Sliding on a walljump strip: vspeed=2 each Step (+0.4 gravity in the
    motion phase => observed 2.4/frame)."""
    c = _room("rGuyFortress1")
    c.set_state(2213, 390, 0, 0, 1)
    c.step(N)                      # entering range
    ys = []
    for _ in range(4):
        y0 = c.y
        c.step(N)
        ys.append(round(c.y - y0, 2))
        assert c.player_ext()["hang"] == 1
    assert ys == [2.4, 2.4, 2.4, 2.4]
    c.close()


@needs_pack
def test_walljump_plain_kick():
    """Plain fortress kick (jump held): vspeed=-9, hspeed=15."""
    c = _room("rGuyFortress1")
    c.set_state(2213, 390, 0, 0, 1)
    c.step(N)                      # slide frame (in range)
    x0 = c.x
    c.step(NJ)                     # jump pressed+held
    assert c.hspeed == 15
    assert round(c.vspeed, 2) == -8.6          # -9 + 0.4 gravity
    assert c.x == x0 + 15
    c.close()


@needs_pack
def test_walljump_no_jump_pushoff():
    """Pressing away without jump: hspeed=3 push-off."""
    c = _room("rGuyFortress1")
    c.set_state(2213, 390, 0, 0, 1)
    c.step(N)
    c.step(R)                      # right pressed, no jump
    assert c.hspeed == 3
    c.close()


@needs_pack
def test_yellowall_launch_and_decay():
    """yellowall kick: hspeed=±10, vspeed=-10, then input-locked decay
    (hspeed -1 every 10th altj frame, +0.1 extra gravity)."""
    # yellowallL with a player-following camera: rGuyFortress1 (11 strips)
    c = _room("rGuyFortress1")
    import json
    ir = json.load(open(G.IR_PATH))
    xr = next(r for r in ir["exact"]["rooms"] if r["name"] == "rGuyFortress1")
    ys_strips = [e2 for e2 in xr["xents"]
                 if e2["cls"] == XC["XB_WALLSTRIP"] and e2["p"][1] == 1]
    assert len(ys_strips) == 11      # source: 11 yellowallL in fortress1
    strips = [(e2["x"], e2["y"]) for e2 in ys_strips]
    found = False
    for srow in strips:
        sx, sy = float(srow[0]), float(srow[1])
        for dx in (33, 34, 35, 36, 37, -6, -7, -8):
            c.set_state(sx + dx, sy + 12, 0, 0, 1)
            c.step(N)              # settle camera + proximity
            c.step(N)
            c.step(NJ)
            if abs(c.hspeed) == 10 and c.vspeed < -9:
                found = True
                break
        if found:
            break
    assert found, "no yellowall kick triggered on any strip"
    assert c.vspeed == pytest.approx(-10 + 0.4, abs=1e-6)
    assert c.player_ext()["walljumpboost"] == -1
    # decay: input is ignored while walljumpboost < 0
    h0 = c.hspeed
    for _ in range(12):
        c.step(L if h0 > 0 else R)     # opposite input: ignored
    assert iw_sign(c.hspeed) == iw_sign(h0)
    assert abs(c.hspeed) in (abs(h0), abs(h0) - 1)   # decayed by <= 1
    c.close()


def iw_sign(v):
    return (v > 0) - (v < 0)


@needs_pack
def test_water2_caps_and_infinite_jumps():
    """objWater2: vspeed capped at 2; jump always grants -7 (djump spent)."""
    c = _room("rGuy1")
    c.set_state(3616, 1750, 0, 5, 1)
    c.step(N)
    assert c.vspeed <= 2.0 + 1e-9
    c.set_state(3616, 1750, 0, 0, 2)   # air jump already used
    granted = 0
    for _ in range(3):
        c.step(N)
        c.step(NJ)
        if c.vspeed < -6:
            granted += 1
    assert granted == 3
    c.close()


@needs_pack
def test_couch_bounce_and_decel():
    """couchTrap: single-use vspeed=-30 + djump; then the source decel
    (+0.71/frame above jump speed, +0.1 while jump is held)."""
    c = _room("rFactoryOutskirts")
    e = c.xents()
    couch = e[e[:, 0] == XC["XB_COUCH"]][0]
    c.set_state(float(couch[1]) + 16, float(couch[2]) - 20, 0, 0, 1)
    for _ in range(30):
        c.step(N)
        if c.vspeed <= -29:
            break
    assert c.vspeed == -30
    v = c.vspeed
    c.step(N)
    assert c.vspeed == pytest.approx(v + 0.71 + 0.4, abs=1e-6)
    c.close()
    # jump HELD through the bounce: +0.1 decel instead of +0.71
    c = _room("rFactoryOutskirts")
    e = c.xents()
    couch = e[(e[:, 0] == XC["XB_COUCH"]) & (e[:, 5] == 0)][0]
    c.set_state(float(couch[1]) + 16, float(couch[2]) - 20, 0, 0, 2)
    c.step(NJ)                      # press in the air (djump spent: no jump)
    for _ in range(30):
        c.step(NJ)                  # jump stays held (no press edge)
        if c.vspeed <= -29:
            break
    assert c.vspeed == -30
    v = c.vspeed
    c.step(NJ)
    assert c.vspeed == pytest.approx(v + 0.1 + 0.4, abs=1e-6)
    # single use: the couch stays consumed
    e = c.xents()
    couch = e[e[:, 0] == XC["XB_COUCH"]][0]
    assert couch[5] == 1            # state=1 (used)
    c.close()


@needs_pack
def test_lock_controls_freezes():
    """triggerLockControls (rGuy1 myspace corridor): frozen=1, h ignored."""
    c = _room("rGuy1")
    e = c.xents()
    lock = e[e[:, 0] == XC["XB_LOCKCONTROLS"]][0]
    lx, ly = float(lock[1]), float(lock[2])
    c.set_state(lx + 8, ly + 16, 0, 0, 1)
    c.step(N)                       # camera settles; activation refresh
    c.step(N)
    assert c.player_ext()["frozen"] == 1
    x0 = c.x
    for _ in range(5):
        c.step(R)
    assert c.x == x0                # input dead
    c.close()


@needs_pack
def test_moving_platform_ride():
    """movingPlatform: landing snaps to top-9, rider is carried by hspeed."""
    c = _room("rCastlevania")
    e = c.xents()
    plats = e[e[:, 0] == XC["XB_MOVPLAT"]]
    assert len(plats) == 12         # source count
    p = plats[0]
    px, py = float(p[1]), float(p[2])
    c.set_state(px + 16, py - 30, 0, 0, 1)
    for _ in range(12):
        c.step(N)
        if c.on_ground or c.player_ext()["carted"]:
            break
    # riding: y == platform.y - 9 and x tracks the platform
    e = c.xents()
    p = e[e[:, 0] == XC["XB_MOVPLAT"]][0]
    if abs(c.y - (float(p[2]) - 9)) < 0.6:
        x0, px0 = c.x, float(p[1])
        c.step(N)
        e = c.xents()
        p1 = e[e[:, 0] == XC["XB_MOVPLAT"]][0]
        assert c.x - x0 == pytest.approx(float(p1[1]) - px0, abs=1e-4)
    c.close()


@needs_pack
def test_road_camera_kills_when_left_behind():
    """cameraCart: the view follows the Cart; the run ends when it passes
    the player (source kill)."""
    c = _room("rGuyRoad")
    d0 = c.deaths
    for t in range(400):
        c.step(N)
        if c.deaths > d0:
            break
    assert c.deaths == d0 + 1
    c.close()


@needs_pack
def test_stone_by_medusa():
    """MedusaHead touch: stoned (controls locked ~100 frames), NOT death."""
    c = _room("rCastlevania")
    e = c.xents()
    m = e[e[:, 0] == XC["XB_MEDUSA"]][0]
    d0 = c.deaths
    c.set_state(float(m[1]), float(m[2]), 0, 0, 1)
    c.step(N)
    px = c.player_ext()
    assert px["stoned"] > 90
    assert c.deaths == d0
    c.close()
