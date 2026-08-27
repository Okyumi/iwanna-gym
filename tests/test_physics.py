"""Physics unit tests against analytic ground truth from the Renex GM8 engine.

Engine constants: 50 Hz, maxSpeed 3, jump -8.5, djump -7, gravity 0.4,
vspeed cap 9, release *0.45. Per-frame applied vertical delta is
vspeed + 0.4 (gravity applies before motion), so:
  full jump rise  = sum(8.1, 7.7, ..., 0.1) = 21 terms = 86.1 px
  djump rise      = sum(6.6, 6.2, ..., 0.2) = 17 terms = 57.8 px
  combined        = 143.9 px ~ 4.5 tiles (engine comment: "jump 4.5 blocks")
  max applied fall speed = 9.0 + 0.4 = 9.4 px/frame
"""
import numpy as np
import pytest

import iwanna_gym as iw

# actions: 2*(h+1) + jump_held
L, LJ, N, NJ, R, RJ = 0, 1, 2, 3, 4, 5

OPEN = (
    "#########################\n" +
    "#.......................#\n" * 17 +
    "#########################\n"
)

SPIKE = (
    "#########################\n" +
    "#.......................#\n" * 16 +
    "#.S..^...............G..#\n" +
    "#########################\n"
)


def make(level=OPEN, **kw):
    kw.setdefault("reward_mode", 0)
    c = iw.CIWanna(level, **kw)
    c.reset()
    return c


def test_walk_speed_exact():
    c = make()
    c.set_state(100.0, 300.0)
    xs = [c.x]
    for _ in range(20):
        c.step(R)
        xs.append(c.x)
    dx = np.diff(xs)
    # horizontal speed is exactly 3 px/frame while airborne/free
    assert np.allclose(dx, 3.0), dx


def test_full_jump_rise():
    c = make()
    # stand on the floor: floor top at y = 18*32 = 576, feet offset +8
    y0 = 576 - 9  # bottom pixel at 543
    c.set_state(400.0, float(y0))
    assert c.on_ground
    c.step(NJ)  # press jump
    ys = [c.y]
    for _ in range(60):
        c.step(NJ)  # keep holding: no release, full arc
        ys.append(c.y)
    rise = y0 - min(ys)
    assert rise == pytest.approx(86.1, abs=1e-9), rise


def test_double_jump_extra_rise():
    c = make()
    y0 = 576 - 9
    c.set_state(400.0, float(y0))
    c.step(NJ)  # ground jump
    apex1 = None
    prev_y = c.y
    for _ in range(60):
        c.step(NJ)
        if c.y >= prev_y:  # just passed apex
            apex1 = prev_y
            break
        prev_y = c.y
    assert apex1 is not None
    c.step(N)          # release jump (one falling frame)
    y_press = c.y      # position from which the air jump fires
    c.step(NJ)         # air jump
    ys = [c.y]
    for _ in range(60):
        c.step(NJ)
        ys.append(c.y)
    rise2 = y_press - min(ys)
    # second arc: applied deltas 6.6, 6.2, ..., 0.2 (17 terms) = 57.8 px
    assert rise2 == pytest.approx(57.8, abs=1e-9), rise2
    # total from ground: 86.1 + 57.8 minus the two post-apex falling frames
    # (+0.3, +0.7) spent detecting the apex = 142.9; perfect timing gives
    # 143.9 px ~ 4.5 tiles (engine comment: "jump 4.5 blocks")
    total = (576 - 9) - min(ys)
    assert total == pytest.approx(142.9, abs=1e-9), total


def test_jump_release_halves_vspeed():
    c = make()
    c.set_state(400.0, 400.0, vspeed=-6.0, djump=1)
    c.act[0] = NJ  # mark jump as held so a release edge can fire
    # set prev_jump_held by stepping once with held (state changes slightly)
    c.step(NJ)
    v_before = c.vspeed
    assert v_before < 0
    c.step(N)  # release
    # release multiplies pre-gravity vspeed by 0.45, then gravity adds 0.4
    assert c.vspeed == pytest.approx(v_before * 0.45 + 0.4, abs=1e-9)


def test_terminal_fall_speed_capped():
    c = make()
    c.set_state(400.0, 100.0)
    ys = [c.y]
    for _ in range(80):
        c.step(N)
        ys.append(c.y)
        if c.on_ground:
            break
    deltas = np.diff(ys)
    assert deltas.max() <= 9.4 + 1e-12
    assert deltas.max() == pytest.approx(9.4, abs=1e-9)


def test_landing_restores_double_jump():
    c = make()
    y0 = 576 - 9
    c.set_state(400.0, float(y0))
    c.step(NJ)          # jump 1 (djump -> 1)
    c.step(N)
    c.step(NJ)          # air jump (djump -> 2)
    assert c.djump == 2
    for _ in range(200):
        c.step(N)
        if c.on_ground:
            break
    assert c.on_ground
    assert c.djump == 1  # player_land() resets to 1


def test_walk_off_ledge_keeps_one_air_jump():
    # djump=1 after leaving ground without jumping -> exactly one air jump
    c = make()
    c.set_state(400.0, 300.0, djump=1)
    c.step(N)
    c.step(NJ)  # air jump should fire (djump 1 -> 2)
    assert c.djump == 2
    v = c.vspeed
    assert v < 0  # moving up after -7 djump


def test_spike_kills():
    c = make(SPIKE, death_penalty=1.0)
    deaths = 0
    for _ in range(400):
        c.step(RJ if c.on_ground else R)
        if c.term[0] and c.last_event == 1:
            deaths += 1
            break
    assert deaths == 1
    assert c.rew[0] == -1.0


def test_goal_reached_terminates_with_reward():
    c = make()
    gx, gy = c.goal
    c.set_state(gx - 40, gy)
    reached = False
    for _ in range(60):
        c.step(R)
        if c.term[0] and c.last_event == 2:
            reached = True
            break
    assert reached
    assert c.rew[0] == pytest.approx(1.0)


def test_timeout_truncates():
    c = make(max_steps=50)
    for t in range(60):
        c.step(N)
        if c.term[0]:
            assert c.last_event == 3
            assert t == 49
            return
    raise AssertionError("no timeout")


def test_solid_collision_stops_at_wall():
    c = make()
    # wall at x=768 (col 24); running right must stop flush at 768-6+... :
    # hitbox right edge +5 => max x with free interior = 762
    c.set_state(700.0, 300.0)
    for _ in range(60):
        c.step(R)
    assert c.x == pytest.approx(762.0, abs=1e-9), c.x


def test_obs_in_bounds():
    env = iw.IWannaEnv(level="tower")
    obs, _ = env.reset(seed=3)
    rng = np.random.default_rng(0)
    for _ in range(2000):
        obs, r, term, trunc, info = env.step(int(rng.integers(6)))
        assert obs.shape == (iw.OBS_SIZE,)
        assert np.all(obs >= -1.0001) and np.all(obs <= 1.0001)
    env.close()
