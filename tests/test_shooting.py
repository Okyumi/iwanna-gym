"""Frame-level tests for source-faithful shooting (IWBTGR values:
playerShoot.gml / objects/bullet.gml / sprBulletMask — spawn (x, y-2),
hspeed ±16, lifetime 42 frames, max 4 alive, one bullet per press edge)."""
from __future__ import annotations

import numpy as np

from iwanna_gym.clib import CIWanna, NUM_ACTIONS, NUM_ACTIONS_LEGACY
from iwanna_gym.levels import load_level

BULLET = 12  # entity type id

L, LJ, N, NJ, R, RJ = 0, 1, 2, 3, 4, 5
SHOOT = 6    # add to any legacy action


def _bullets(c):
    e = c.entities()
    return e[e[:, 0] == BULLET]


def test_action_space_constants():
    assert NUM_ACTIONS == 12
    assert NUM_ACTIONS_LEGACY == 6


def test_bullet_spawn_position_and_velocity():
    c = CIWanna(load_level("flat"), seed=1)
    c.reset()
    x0, y0 = c.x, c.y
    c.step(N + SHOOT)                      # idle + shoot (press edge)
    b = _bullets(c)
    assert len(b) == 1
    # spawned at (x0, y0-2), then moved +16 in the same frame's update
    assert b[0][1] == x0 + 16.0
    assert b[0][2] == y0 - 2.0
    assert b[0][3] == 16.0                 # hspeed = facing(+1) * 16
    c.close()


def test_bullet_faces_left():
    c = CIWanna(load_level("flat"), seed=1)
    c.reset()
    c.step(L)                              # face left
    x0, y0 = c.x, c.y
    c.step(N + SHOOT)
    b = _bullets(c)
    assert b[0][3] == -16.0
    assert b[0][1] == x0 - 16.0
    assert b[0][2] == y0 - 2.0
    c.close()


def test_one_bullet_per_press_edge():
    c = CIWanna(load_level("flat"), seed=1)
    c.reset()
    for _ in range(10):                    # held: single press edge
        c.step(N + SHOOT)
    assert len(_bullets(c)) == 1
    c.step(N)                              # release
    c.step(N + SHOOT)                      # press again
    assert len(_bullets(c)) == 2
    c.close()


def test_bullet_cap_is_four():
    c = CIWanna(load_level("flat"), seed=1)
    c.reset()
    for _ in range(8):                     # 8 press edges in 16 frames
        c.step(N + SHOOT)
        c.step(N)
    assert len(_bullets(c)) == 4           # bullet_number() < 4 in source
    c.close()


def test_bullet_lifetime_42_frames():
    """alarm[0]=42: the bullet exists for 42 frames (41 moves; the alarm
    fires before movement on frame 42, exactly as in GM)."""
    c = CIWanna(load_level("flat"), seed=1)
    c.reset()
    c.step(NJ + SHOOT)                     # fire: bullet frame 1 (move #1)
    for _ in range(40):
        c.step(N)                          # bullet frames 2..41
    b = _bullets(c)
    assert len(b) == 1                     # alive on frame 41
    assert b[0][1] == c.x + 16.0 * 41      # exactly 41 moves of 16 px
    c.step(N)                              # frame 42: alarm fires pre-move
    assert len(_bullets(c)) == 0
    c.close()


def test_bullet_destroyed_by_wall():
    lvl = ("#########\n"
           "#.......#\n"
           "#.......#\n"
           "#S......#\n"
           "#########\n")
    c = CIWanna(lvl, seed=1)
    c.reset()
    c.step(N + SHOOT)
    assert len(_bullets(c)) == 1
    for _ in range(20):
        c.step(N)
    assert len(_bullets(c)) == 0           # hit the right wall and died
    c.close()


def test_shooting_while_moving():
    c = CIWanna(load_level("flat"), seed=1)
    c.reset()
    xs = []
    for k in range(6):
        c.step((R + SHOOT) if k % 2 == 0 else R)   # run right, fire every 2
        b = _bullets(c)
        if len(b):
            xs.append(sorted(b[:, 1]))
    b = _bullets(c)
    assert len(b) == 3
    # every bullet outruns the player (16 vs 3 px/frame)
    assert all(bx > c.x for bx in b[:, 1])
    c.close()


def test_full_space_movement_matches_legacy():
    """Actions a and a+6 produce identical movement (shoot changes nothing
    about the Kid's kinematics)."""
    seq = [R, RJ, R, R, NJ, N, L, LJ, R, RJ, R, R] * 20

    def run(shift):
        c = CIWanna(load_level("needle"), seed=9)
        c.reset()
        traj = []
        for a in seq:
            c.step(a + shift)
            traj.append((c.x, c.y, c.vspeed, c.djump))
        c.close()
        return traj

    assert run(0) == run(SHOOT)


def test_legacy_actions_spawn_no_bullets():
    c = CIWanna(load_level("flat"), seed=1)
    c.reset()
    for a in (L, LJ, N, NJ, R, RJ) * 10:
        c.step(a)
    assert len(_bullets(c)) == 0
    c.close()


def test_deterministic_replay_with_shooting():
    def run():
        c = CIWanna(load_level("trap"), seed=5, checkpoint_respawn=True)
        c.reset()
        traj = []
        for t in range(600):
            c.step((t * 7 + 3) % 12)       # full action space incl. shoot
            traj.append((c.x, c.y, c.vspeed, c.ent_count, c.deaths))
        c.close()
        return traj

    assert run() == run()
