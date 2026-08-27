"""Solvability probes for the 20 trap rooms.

Each probe is a generator of actions driven by live state (player x/y,
ground flag) — simple x-threshold rules a careful human player would use.
A room passes when the scripted run reaches the goal with zero deaths.

Actions: 0=left 2=idle 4=right (+1 = jump held).
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
from iwanna_gym.env import IWannaEnv  # noqa: E402

TILE = 32


# ---- probe helpers (generators yield actions) ----

def run_to(env, x, a=4):
    while env.c.x < x:
        yield a


def run_back_to(env, x):
    while env.c.x > x:
        yield 0


def wait(n):
    for _ in range(n):
        yield 2


def full_jump(move=4, hold=24, land_env=None):
    """Hold jump while moving; then keep moving until landing."""
    for _ in range(hold):
        yield move + 1
    if land_env is not None:
        while land_env.c.obs[5] < 0.5:
            yield move
    else:
        for _ in range(30):
            yield move


def hop(move=4, hold=6):
    for _ in range(hold):
        yield move + 1


def double_jump(move=4, first=20, gap=4, second=20):
    for _ in range(first):
        yield move + 1
    for _ in range(gap):
        yield move
    for _ in range(second):
        yield move + 1


def _steer(env, xt):
    if env.c.x < xt - 4:
        return 4
    if env.c.x > xt + 4:
        return 0
    return 2


def jump_towards(env, xt, first=22, gap=4, second=22):
    """Double-jump while steering toward x-target, then land."""
    for held, n in ((1, first), (0, gap), (1, second)):
        for _ in range(n):
            yield _steer(env, xt) + held
    while env.c.obs[5] < 0.5:
        yield _steer(env, xt)


def _low_bullet_near(env, dist=90):
    for r in env.c.entities():
        if r[0] == 5 and r[3] < 0 and 0 < r[1] - env.c.x < dist \
                and r[2] > env.c.y - 30:
            return True
    return False


def dodge_run(env, x_target):
    """Run right, hopping over incoming floor-level bullets."""
    while env.c.x < x_target:
        if _low_bullet_near(env) and env.c.obs[5] > 0.5:
            yield from hop(move=4, hold=10)
        else:
            yield 4


def dodge_wait(env, n):
    """Stand in place, hopping over incoming floor-level bullets."""
    t = 0
    while t < n:
        if _low_bullet_near(env, dist=60) and env.c.obs[5] > 0.5:
            for _ in range(10):
                yield 3
                t += 1
            while env.c.obs[5] < 0.5:
                yield 2
                t += 1
        else:
            yield 2
            t += 1


# ---- per-room probes ----

def p_t01(env):
    # trigger the apple from a safe distance, wait for it to fly offscreen
    yield from run_to(env, 11 * TILE + 12)
    yield from wait(90)
    yield from run_to(env, 24 * TILE)


def p_t02(env):
    # constant sprint passes under the volley
    yield from run_to(env, 24 * TILE)


def p_t03(env):
    # trigger the riser, wait for it to freeze, jump over the spike wall
    yield from run_to(env, 8 * TILE + 12)
    yield from wait(60)
    yield from run_to(env, 10 * TILE + 16)
    yield from double_jump()
    yield from run_to(env, 24 * TILE)


def p_t04(env):
    # hop across the collapsing platforms without lingering
    yield from run_to(env, 8 * TILE)
    yield from double_jump(first=22, gap=3, second=16)   # onto platform 1
    yield from double_jump(first=20, gap=3, second=16)   # onto platform 2 / past
    while env.c.obs[5] < 0.5:
        yield 4
    yield from run_to(env, 24 * TILE)


def p_t05(env):
    # door shuts behind; tag the save; exit opens
    yield from run_to(env, 12 * TILE + 16)
    yield from run_to(env, 24 * TILE)


def p_t06(env):
    # enter the crusher region, back off, let it fall, then pass
    yield from run_to(env, 9 * TILE)
    yield from run_back_to(env, 8 * TILE - 16)
    yield from wait(80)
    yield from run_to(env, 24 * TILE)


def p_t07(env):
    # jump each incoming bullet
    while env.c.x < 24 * TILE:
        bullets = [r for r in env.c.entities() if r[0] == 5]
        near = [b for b in bullets
                if 0 < b[1] - env.c.x < 90 and b[3] < 0]
        if near and env.c.obs[5] > 0.5:
            yield from hop(move=4, hold=10)
        else:
            yield 4


def p_t08(env):
    # never stop running
    yield from run_to(env, 24 * TILE)


def p_t09(env):
    # touch the fake save, back off while both fruits drop, then proceed
    yield from run_to(env, 12 * TILE + 4)
    yield from run_back_to(env, 10 * TILE)
    yield from wait(70)
    yield from run_to(env, 24 * TILE)


def p_t10(env):
    # launch the fruit, stay left of its landing column until it is culled,
    # then run through the opened gate
    yield from run_to(env, 6 * TILE + 12)
    yield from wait(110)
    yield from run_to(env, 24 * TILE)


def p_t11(env):
    # jump over the ground-level teleport field at cols 11-12
    yield from run_to(env, 9 * TILE + 16)
    yield from double_jump(first=24, gap=3, second=20)
    while env.c.obs[5] < 0.5:
        yield 4
    yield from run_to(env, 24 * TILE)


def p_t12(env):
    # pause after each dropper trigger, then continue
    for trig in (6, 11, 16):
        yield from run_to(env, trig * TILE + 12)
        yield from wait(55)
    yield from run_to(env, 24 * TILE)


def p_t13(env):
    # jump the whole bridge; it opens mid-air beneath you
    yield from run_to(env, 8 * TILE + 20)
    yield from double_jump(first=24, gap=3, second=22)
    while env.c.obs[5] < 0.5:
        yield 4
    yield from run_to(env, 24 * TILE)


def p_t14(env):
    # just run — beat the rising flood
    yield from run_to(env, 24 * TILE)


def p_t15(env):
    # sprint with small waits when a fruit is inbound overhead
    while env.c.x < 24 * TILE:
        fruits = [r for r in env.c.entities() if r[0] == 2]
        danger = [f for f in fruits
                  if abs(f[1] - env.c.x) < 70 and f[2] > env.c.y - 160]
        yield 2 if danger else 4


def p_t16(env):
    # region activates the bridge; hop across the two platforms
    yield from run_to(env, 8 * TILE)
    yield from double_jump(first=24, gap=3, second=20)   # onto platform 1
    while env.c.obs[5] < 0.5:
        yield 4
    yield from double_jump(first=18, gap=3, second=14)   # onto platform 2
    while env.c.obs[5] < 0.5:
        yield 4
    yield from double_jump(first=14, gap=3, second=10)   # off to the floor
    while env.c.obs[5] < 0.5:
        yield 4
    yield from run_to(env, 24 * TILE)


def p_t17(env):
    # sprint through the bullet wall hopping the low shot,
    # then jump the fruit that pops out of the floor at col 20
    yield from dodge_run(env, 18 * TILE + 16)
    yield from double_jump(first=24, gap=3, second=20)
    while env.c.obs[5] < 0.5:
        yield 4
    yield from run_to(env, 24 * TILE)


def p_t18(env):
    # climb the platform ladder; each landing calls a shot at that height,
    # so keep moving upward
    yield from run_to(env, 9 * TILE)
    yield from jump_towards(env, 10 * TILE + 16)          # platform 1
    yield from wait(4)
    yield from jump_towards(env, 16 * TILE + 16)          # platform 2
    yield from wait(4)
    yield from jump_towards(env, 20 * TILE + 16)          # goal at (20,12)
    for _ in range(60):
        yield _steer(env, 20 * TILE + 16) + 1


def p_t19(env):
    # hit the save and sprint through before the timer closes the gate
    yield from run_to(env, 24 * TILE)


def p_t20(env):
    # finale: trigger the apple, wait for it to fly off (hopping timer
    # bullets), cross the collapsing platform over the spikes, tag the
    # save, sprint the opened exit gate
    yield from dodge_run(env, 7 * TILE + 12)
    yield from dodge_wait(env, 70)                        # apple culled
    yield from dodge_run(env, 11 * TILE)
    yield from jump_towards(env, 13 * TILE + 16)          # collapsing platform
    yield from hop(move=4, hold=9)                        # off, over spike edge
    while env.c.obs[5] < 0.5:
        yield 4
    yield from dodge_run(env, 24 * TILE)                  # through save + gate


from iwanna_gym.levels import list_levels  # noqa: E402

_ROOMS = [n.split("/", 1)[1] for n in list_levels() if n.startswith("traps/")]
PROBES = {room: globals()["p_" + room.split("_")[0]] for room in _ROOMS}


def run_probe(room, fn, max_steps=3000, record=None):
    env = IWannaEnv(level=f"traps/{room}", max_steps=max_steps,
                    death_penalty=1.0)
    env.reset(seed=0)
    frames = []
    acts = []
    t = 0
    for a in fn(env):
        obs, r, term, trunc, info = env.step(int(a))
        acts.append(int(a))
        if record is not None:
            frames.append(env.render())
        t += 1
        ev = env.c.last_event
        if term or trunc:
            return ev == 2, t, ev, acts, frames
        if t >= max_steps:
            break
    # generator exhausted without terminal: keep idling briefly
    for _ in range(100):
        obs, r, term, trunc, info = env.step(2)
        acts.append(2)
        if record is not None:
            frames.append(env.render())
        t += 1
        if term or trunc:
            return env.c.last_event == 2, t, env.c.last_event, acts, frames
    return False, t, 0, acts, frames


def main():
    only = sys.argv[1:] or None
    passed = failed = 0
    for room in sorted(PROBES):
        if only and not any(room.startswith(o) for o in only):
            continue
        ok, t, ev, _, _ = run_probe(room, PROBES[room])
        status = "PASS" if ok else f"FAIL(ev={ev})"
        print(f"{room:16s} {status:10s} steps={t}")
        passed += ok
        failed += (not ok)
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
