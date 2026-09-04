"""Discovery runtime semantics (docs/discovery_benchmark_contract.md).

Covers, at the environment/protocol interface and without any RL
library: the task/attempt boundaries, the memory-boundary protocol,
deterministic replay from (task seed, action sequence), the paired
anti-leakage property of the observable observation mode, the renderer
dormancy fix, and native-vs-Gymnasium parity (the Gymnasium env and the
PufferLib binding drive the same c_reset/c_step; the parity test drives
the native path directly through the shared library).

All rooms below are synthetic test fixtures (invented layouts).
"""
from __future__ import annotations

import os

import numpy as np
import pytest

import sys
sys.path.insert(0, ".")
from iwanna_gym.clib import OBS_SIZE, CIWanna              # noqa: E402
from iwanna_gym.env import IWannaDiscoveryEnv, IWannaEnv   # noqa: E402

# ------------------------------------------------------------------ #
# paired rooms: identical VISIBLE scene, different hidden state.
# The trap parks at tile (8,2) as a down-spike; the trigger region and
# the launch parameters are invisible; 'G' is reachable on the ground.
# ------------------------------------------------------------------ #

_BASE = """\
#########################
#.......................#
#.......................#
#.......................#
#.......................#
#.......................#
#.......................#
#.......................#
#.......................#
#S.....................G#
#########################
"""

# pair 1: same world, but B's trap is made harmless at room start —
# simulator truth differs from step 0, appearance never does (a dormant
# deadly trap and a dormant harmless one draw identically).
ROOM_DEADLY = _BASE + """\
@trap 8 2 dir=down vy=7 id=1 tag=17
@trigger 20 9 id=1 w=1 h=2
"""
ROOM_DISARMED = _BASE + """\
@trap 8 2 dir=down vy=7 id=1 tag=17
@trigger 20 9 id=1 w=1 h=2
!when=room_enter -> make_harmless tag=17
"""

# pair 2: same parked trap, different hidden WIRING — A's trigger sits
# at column 5 with launch vy=7, B's at column 11 with vy=9.
ROOM_WIRE_A = _BASE + """\
@trap 8 2 dir=down vy=7 id=1 tag=17
@trigger 5 9 id=1 w=1 h=3
"""
ROOM_WIRE_B = _BASE + """\
@trap 8 2 dir=down vy=9 id=1 tag=17
@trigger 11 9 id=1 w=1 h=3
"""


def _mk(room: str, obs_mode: str, **kw) -> IWannaDiscoveryEnv:
    e = IWannaDiscoveryEnv(level=room, obs_mode=obs_mode,
                           attempts_K=kw.pop("attempts_K", 5),
                           attempt_frames_H=kw.pop("attempt_frames_H", 400),
                           reward_mode="sparse", **kw)
    e.reset(seed=0, options={"task_seed": 4242})
    return e


# ------------------------------------------------------------------ #
# 1. attempt vs task boundaries
# ------------------------------------------------------------------ #

def test_death_is_attempt_boundary_not_episode_end():
    e = _mk(ROOM_DEADLY, "observable_vector", attempts_K=3)
    # sprint right: cross the trigger at column 20 -> the trap launches
    # far behind us; instead die by attempt timeout? No: walk left into
    # nothing. Use the pair-2 room where the trigger is on our path.
    e.close()
    e = _mk(ROOM_WIRE_A, "observable_vector", attempts_K=3,
            attempt_frames_H=2000)
    boundaries, terms = 0, 0
    for _ in range(6000):
        obs, r, term, trunc, info = e.step(4)         # run right
        if info["attempt_ended"] and not info["task_ended"]:
            boundaries += 1
            assert not term, "attempt boundary must NOT terminate"
            assert info["attempt_id"] == boundaries + 1
        if term:
            terms += 1
            assert info["task_ended"]
            break
    assert boundaries == 2 and terms == 1, (boundaries, terms)
    assert e.c.last_task_attempts == 3
    e.close()


def test_task_ends_only_on_success_or_budget():
    # no hazard on the path when the trigger is behind the start: the
    # runner reaches G -> task success on attempt 1
    e = _mk(ROOM_DEADLY, "observable_vector", attempts_K=4)
    for _ in range(4000):
        obs, r, term, trunc, info = e.step(4)
        if term:
            break
    # crossing column 20 launches the trap at column 8 (behind us) so
    # the goal at column 23 is reached alive
    assert term and info["task_ended"] and info["task_success"]
    assert info["final_task_attempts"] == 1
    assert info["final_task_deaths"] == 0
    e.close()


def test_attempt_frame_budget_consumes_attempt():
    e = _mk(ROOM_DEADLY, "observable_vector", attempts_K=2,
            attempt_frames_H=50)
    ended, term = 0, False
    for _ in range(200):
        obs, r, term, trunc, info = e.step(2)          # stand still
        if info["attempt_ended"]:
            ended += 1
        if term:
            break
    assert ended == 2 and term and not info["task_success"]
    e.close()


def test_task_reset_vs_attempt_reset_mechanically_distinct():
    e = _mk(ROOM_WIRE_A, "observable_vector")
    # die once: world restores, task identity (seed) unchanged
    seed0 = e.c.task_seed
    for _ in range(3000):
        obs, r, term, tr, info = e.step(4)
        if info["attempt_ended"]:
            break
    assert e.c.task_seed == seed0 and info["attempt_id"] == 2
    assert info["death_count"] == 1
    # task reset: new attempt counter; explicit seed pin honored
    obs, info = e.reset(options={"task_seed": 777})
    assert info["attempt_id"] == 1 and info["death_count"] == 0
    assert info["task_seed"] == 777
    e.close()


# ------------------------------------------------------------------ #
# 2. the memory boundary, protocol-level (no RL library)
# ------------------------------------------------------------------ #

class _EpisodicMemory:
    """Stand-in for any cross-attempt agent memory: records where each
    death happened. The PROTOCOL is: keep it while the task lives,
    clear it exactly when the task ends / on task reset."""

    def __init__(self):
        self.deaths: list[float] = []

    def observe(self, info):
        if info["attempt_ended"]:
            self.deaths.append(info["x"])

    def task_boundary(self):
        self.deaths.clear()


def test_memory_persists_across_attempts_and_clears_on_task_reset():
    e = _mk(ROOM_WIRE_A, "observable_vector", attempts_K=3,
            attempt_frames_H=2000)
    mem = _EpisodicMemory()
    for _ in range(9000):
        obs, r, term, tr, info = e.step(4)
        mem.observe(info)
        if info["attempt_ended"] and not term:
            # attempt boundary: env did not terminate, so nothing forced
            # a memory cut — the evidence accumulates
            assert len(mem.deaths) >= 1
        if term:
            break
    assert len(mem.deaths) == 3          # one entry per attempt's death
    # deaths cluster at the same hidden hazard: the memory carries
    # usable information (this is what a discovery agent consumes)
    assert max(mem.deaths) - min(mem.deaths) < 64.0
    # task boundary: the protocol clears agent memory
    assert term and info["task_ended"]
    mem.task_boundary()
    e.reset(options={"task_seed": 999})
    assert mem.deaths == []
    e.close()


# ------------------------------------------------------------------ #
# 3. deterministic replay from (task seed, action sequence)
# ------------------------------------------------------------------ #

def test_replay_bit_identical_across_attempts_and_instances():
    acts = ([4] * 40 + [5] * 10 + [4] * 60) * 40
    traj = []
    for gym_seed in (0, 1234):           # gym seed must not matter
        e = _mk(ROOM_WIRE_B, "observable_vector")
        e.reset(seed=gym_seed, options={"task_seed": 31337})
        rec = []
        for a in acts:
            obs, r, term, tr, info = e.step(a)
            rec.append((obs.tobytes(), r, term, info["attempt_id"]))
            if term:
                break
        traj.append(rec)
        e.close()
    assert traj[0] == traj[1]


# ------------------------------------------------------------------ #
# 4. paired anti-leakage
# ------------------------------------------------------------------ #

def test_privileged_distinguishes_hidden_deadliness_observable_does_not():
    # (the room_enter disarm event runs inside the first step)
    ea = _mk(ROOM_DEADLY, "privileged_vector")
    eb = _mk(ROOM_DISARMED, "privileged_vector")
    ea.reset(options={"task_seed": 1})
    eb.reset(options={"task_seed": 1})
    oa = ea.step(2)[0]
    ob = eb.step(2)[0]
    assert not np.array_equal(oa, ob), \
        "privileged mode must see the disarmed trap's flag"
    ea.close(); eb.close()

    ea = _mk(ROOM_DEADLY, "observable_vector")
    eb = _mk(ROOM_DISARMED, "observable_vector")
    ea.reset(options={"task_seed": 1})
    eb.reset(options={"task_seed": 1})
    # identical visible histories stay identical while nothing manifests
    for _ in range(60):
        ra = ea.step(2); rb = eb.step(2)          # stand still
        assert np.array_equal(ra[0], rb[0]), \
            "observable mode leaked simulator-only deadliness"
    ea.close(); eb.close()


def test_hidden_wiring_identical_until_visible_consequence():
    ea = _mk(ROOM_WIRE_A, "observable_vector")
    eb = _mk(ROOM_WIRE_B, "observable_vector")
    ea.reset(options={"task_seed": 7})
    eb.reset(options={"task_seed": 7})
    diverged_at = None
    for t in range(400):
        ra = ea.step(4); rb = eb.step(4)          # run right
        if not np.array_equal(ra[0], rb[0]):
            diverged_at = t
            break
    # A's trigger is at column 5: the trap launches (visible motion)
    # only after the player crosses it — never on the first frames
    assert diverged_at is not None and diverged_at > 5
    # and the divergence coincides with A's trap having launched
    trap_a = [row for row in ea.c.entities() if int(row[0]) == 4][0]
    assert trap_a[6] == 0.0 or trap_a[4] != 0.0    # no longer dormant
    ea.close(); eb.close()


def test_dormant_trap_renders_identically_to_static_spike():
    from iwanna_gym.render import (SPIKE, TRAP_DORMANT, TRAP_LIVE,
                                   render_frame, render_tiles)
    assert np.array_equal(TRAP_DORMANT, SPIKE)
    assert np.array_equal(TRAP_LIVE, SPIKE)
    # a parked down-trap cell must be pixel-identical to a static
    # down-spike tile cell
    room = _BASE + "@trap 8 2 dir=down vy=7 id=1\n"
    e = IWannaEnv(level=room.replace(".....................G",
                                     "...........v.........G"))
    e.reset(seed=0)
    img = render_frame(render_tiles(e.c.tiles()), e.c.x, e.c.y,
                       goal=e.c.goal, entities=e.c.entities())
    # trap entity center = (8*32+16, 2*32+16) -> its 32px cell; the
    # static 'v' spike sits at tile (13, 9)
    trap_cell = img[2 * 32:3 * 32, 8 * 32:9 * 32]
    spike_cell = img[9 * 32:10 * 32, 13 * 32:14 * 32]
    assert np.array_equal(trap_cell, spike_cell)
    e.close()


# ------------------------------------------------------------------ #
# 5. pack-mode leak check (source-built pack; skipped when absent)
# ------------------------------------------------------------------ #

PACK = "build/games/iwbtgr_1_5_3.iwpack"


@pytest.mark.skipif(not os.path.exists(PACK),
                    reason="local source-built pack required")
def test_pack_unmanifested_xents_hidden_from_observable_mode():
    # rGuyFortress1 spawn: 9 unarmed maskless Fire hazards ahead — the
    # privileged vector may see them, the observable vector must not.
    def spawn_obs(mode):
        e = IWannaDiscoveryEnv(game="iwbtgr_1_5_3", mode="room",
                               room_id="rGuyFortress1", obs_mode=mode,
                               attempts_K=3, attempt_frames_H=300)
        obs, _ = e.reset(seed=0, options={"task_seed": 5})
        ents = obs[OBS_SIZE - 30:].reshape(6, 5).copy()
        e.close()
        return obs, ents

    obs_p, ents_p = spawn_obs("privileged_vector")
    obs_o, ents_o = spawn_obs("observable_vector")
    assert not np.array_equal(obs_p, obs_o), \
        "modes identical at the fortress spawn — the filter is dead"

    # ground truth from the drawn-status introspection: positions of
    # every alive+active UNDRAWN xent must appear in no observable slot
    e = IWannaDiscoveryEnv(game="iwbtgr_1_5_3", mode="room",
                           room_id="rGuyFortress1",
                           obs_mode="observable_vector",
                           attempts_K=3, attempt_frames_H=300)
    obs, _ = e.reset(seed=0, options={"task_seed": 5})
    ents = obs[OBS_SIZE - 30:].reshape(6, 5)
    x = e.c.xents()
    drawn = e.c.xents_drawn()
    assert len(drawn) == len(x)
    px, py = e.c.x, e.c.y
    W = e.c.tw * 32.0
    H = e.c.th * 32.0
    hidden = [(row[1], row[2]) for row, d in zip(x, drawn)
              if row[6] and row[7] and not d]
    assert hidden, "fortress spawn should have unmanifested entities"
    for hx, hy in hidden:
        ndx, ndy = (hx - px) / W, (hy - py) / H
        for slot in ents:
            if np.abs(slot).sum() == 0:
                continue
            assert abs(slot[0] - ndx) + abs(slot[1] - ndy) > 1e-6, \
                "observable obs contains an undrawn entity"
    e.close()


@pytest.mark.skipif(not os.path.exists(PACK),
                    reason="local source-built pack required")
def test_pack_discovery_checkpoint_restore_and_replay():
    e = IWannaDiscoveryEnv(game="iwbtgr_1_5_3", mode="room",
                           room_id="rGuy1", obs_mode="observable_vector",
                           attempts_K=3, attempt_frames_H=400)

    def run():
        e.reset(seed=0, options={"task_seed": 11})
        rec = []
        for t in range(900):
            a = 4 if (t // 50) % 2 == 0 else 5
            obs, r, term, tr, info = e.step(a)
            rec.append((obs.tobytes(), r, term, info["attempt_id"],
                        info["room_id"]))
            if term:
                break
        return rec

    r1, r2 = run(), run()
    assert r1 == r2, "pack-mode discovery replay must be bit-identical"
    e.close()


# ------------------------------------------------------------------ #
# 6. native/PufferLib-path vs Gymnasium parity
# ------------------------------------------------------------------ #

def test_native_and_gym_paths_produce_identical_trajectories():
    """The PufferLib binding and the Gymnasium env drive the same
    c_reset/c_step; this drives that native path directly through the
    shared library with the same config and asserts bit-identical
    observations, rewards, terminals and boundary flags."""
    acts = ([4] * 30 + [5] * 8 + [2] * 5) * 120

    gym_env = IWannaDiscoveryEnv(level=ROOM_WIRE_A,
                                 obs_mode="observable_vector",
                                 attempts_K=4, attempt_frames_H=300,
                                 reward_mode="sparse")
    gym_env.reset(seed=0, options={"task_seed": 202})

    c = CIWanna(ROOM_WIRE_A, max_steps=4 * 300, reward_mode=0,
                death_penalty=1.0, seed=555)
    c.set_discovery(4, 300, 1)
    c.set_task_seed(202)
    c.reset()

    for a in acts:
        og, rg, tg, _, ig = gym_env.step(a)
        c.step(a)
        assert np.array_equal(og, c.obs)
        assert rg == float(c.rew[0])
        assert tg == bool(c.term[0])
        assert ig["attempt_ended"] == c.attempt_ended
        assert ig["task_ended"] == c.task_ended
        if tg:
            break
    assert c.task_ended and bool(ig["task_ended"])
    assert ig["final_task_attempts"] == c.last_task_attempts
    assert ig["final_task_deaths"] == c.last_task_deaths
    gym_env.close(); c.close()


def test_binding_c_compiles_against_stub_harness(tmp_path=None):
    """Compile-checks c_src/binding.c (the PufferLib Ocean entry) against
    a minimal stub of pufferlib's env_binding.h, so a binding drift
    (missing kwarg, renamed Log field) fails here instead of inside a
    pufferlib checkout."""
    import pathlib
    import subprocess
    import tempfile
    td = pathlib.Path(tempfile.mkdtemp(prefix="iwbind_"))
    (td / "env_binding.h").write_text(
        "/* stub of pufferlib env_binding.h (syntax check only) */\n"
        "#include <stdint.h>\n"
        "typedef void PyObject;\n"
        "static double unpack(PyObject* kwargs, const char* key);\n"
        "static int assign_to_dict(PyObject* d, const char* k, double v);\n"
        "static int my_init(Env* env, PyObject* a, PyObject* kw);\n"
        "static int my_log(PyObject* dict, Log* log);\n")
    # binding.c includes "../env_binding.h"; a -I dir one level below
    # the stub resolves it (dir-of-file search finds nothing in c_src)
    sub = td / "sub"
    sub.mkdir()
    r = subprocess.run(["gcc", "-fsyntax-only", "-DIW_NO_RAYLIB",
                        "-I", str(sub), "c_src/binding.c"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]


# ------------------------------------------------------------------ #
# 7. legacy behavior is untouched
# ------------------------------------------------------------------ #

def test_legacy_env_unchanged_by_discovery_machinery():
    e = IWannaEnv(level="gaps", reward_mode="dense")
    obs, info = e.reset(seed=3)
    assert e.c.obs_mode == 0 and "task_ended" not in info
    # a legacy death still terminates the episode
    term = False
    for _ in range(2000):
        obs, r, term, tr, info = e.step(4)
        if term:
            break
    assert term
    e.close()
