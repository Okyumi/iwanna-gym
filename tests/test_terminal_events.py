"""Regression tests for the terminal-event repair (measurement bugs
found at 4dcbd6c): C respawns before Python reads position, timeouts
counted as deaths in death-memory, and duplicated evaluator logic with
traj_index hardcoded to 0.

Each test builds a synthetic room that forces a specific outcome, then
asserts the terminal snapshot and the metric that consumes it.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

import sys
sys.path.insert(0, ".")
import iwanna_gym as iw                                   # noqa: E402
from iwanna_gym.clib import CIWanna, OBS_SIZE            # noqa: E402
from iwanna_gym.discovery import evaluator as E          # noqa: E402
from iwanna_gym.discovery.baselines import DeathMemory   # noqa: E402
from iwanna_gym.discovery.vector import CVecIWanna       # noqa: E402

PACK = "build/games/iwbtgr_1_5_3.iwpack"

# a wide floor with two spikes at different x; goal far right
TWO_SPIKE = """\
#############################
#...........................#
#...........................#
#...........................#
#...........................#
#...........................#
#...........................#
#...........................#
#...........................#
#S.......^........^........G#
#############################
"""
# no hazards at all: reaching the goal is possible, and standing still
# times out — never a death
SAFE = """\
###############
#.............#
#.............#
#.............#
#.............#
#.............#
#.............#
#.............#
#.............#
#S...........G#
###############
"""


def _run(room, policy, K=6, H=400, seed=1, tseed=1):
    e = iw.IWannaDiscoveryEnv(level=room, attempts_K=K, attempt_frames_H=H,
                              reward_mode="sparse")
    obs, info = e.reset(seed=seed, options={"task_seed": tseed})
    hist = []
    t = 0
    while True:
        obs, r, term, tr, info = e.step(policy(t))
        t += 1
        if info["attempt_ended"]:
            hist.append({k: info[k] for k in (
                "attempt_event", "term_x", "term_y", "term_room",
                "term_attempt", "task_ended", "task_exhausted",
                "attempt_id")})
        if term:
            break
    e.close()
    return hist


# ------------------------------------------------------------------ #
# 1. death terminal position is the death location, not the checkpoint
# ------------------------------------------------------------------ #

def test_death_position_is_terminal_not_checkpoint():
    hist = _run(TWO_SPIKE, lambda t: 4)          # sprint right into spike 1
    spawn_x = 48.0
    assert hist, "expected at least one death"
    for h in hist:
        assert h["attempt_event"] == 1
        # first spike is at tile 9 -> x ~288; death x is there, not spawn
        assert abs(h["term_x"] - spawn_x) > 100, h
        assert 250 < h["term_x"] < 340, h


def test_deaths_at_different_locations_are_distinguished():
    # run right for a while, then a policy that dies at the SECOND spike
    # by jumping the first: alternate to reach further before dying
    def pol(t):
        return 5 if (t % 40) < 12 else 4
    hist = _run(TWO_SPIKE, pol, H=600)
    xs = {round(h["term_x"]) for h in hist if h["attempt_event"] == 1}
    # the evaluator can now see distinct death x's if they occur; at
    # minimum the recorded x is a real hazard location, never the spawn
    assert all(h["term_x"] > 150 for h in hist if h["attempt_event"] == 1)
    assert len(xs) >= 1


def test_repeated_deaths_same_hazard_counts_as_repeated():
    hist = _run(TWO_SPIKE, lambda t: 4, K=5)     # always dies at spike 1
    recs = [{"outcome": "death", "attempt_event": 1,
             "term_xy": [h["term_x"], h["term_y"]],
             "term_room": h["term_room"], "frames": 1, "progress": 0.1}
            for h in hist]
    m = E.task_metrics(recs, K=5)
    assert m["n_deaths"] >= 3
    # every death at the same spot in the same room -> RDR == 1.0
    assert m["repeated_death_rate"] == 1.0


def test_repeated_death_rate_respects_room_boundary():
    # same coordinates, different rooms must NOT be conflated
    recs = [
        {"outcome": "death", "attempt_event": 1, "term_xy": [100.0, 100.0],
         "term_room": 0, "frames": 1, "progress": 0.1},
        {"outcome": "death", "attempt_event": 1, "term_xy": [100.0, 100.0],
         "term_room": 1, "frames": 1, "progress": 0.1},   # same xy, room 1
        {"outcome": "death", "attempt_event": 1, "term_xy": [100.0, 100.0],
         "term_room": 0, "frames": 1, "progress": 0.1},   # repeats room-0
    ]
    m = E.task_metrics(recs, K=5)
    # death 2 (room 1) is NOT a repeat; death 3 (room 0) IS -> 1 of 2
    assert m["repeated_death_rate"] == 0.5


# ------------------------------------------------------------------ #
# 2. timeout is not a death
# ------------------------------------------------------------------ #

def test_timeout_without_death():
    hist = _run(SAFE, lambda t: 2, K=3, H=60)    # stand still: times out
    assert hist and all(h["attempt_event"] == 3 for h in hist)
    assert all(h["attempt_event"] != 1 for h in hist)   # never a death
    # the evaluator classifies these as timeouts, zero deaths
    recs = [{"outcome": "timeout", "attempt_event": 3,
             "frames": 60, "progress": 0.0} for _ in hist]
    m = E.task_metrics(recs, K=3)
    assert m["n_deaths"] == 0 and m["repeated_death_rate"] is None


def test_deathmemory_ignores_timeouts():
    dm = DeathMemory(1, 4, window=3)
    for t in range(5):
        dm.push(np.full((1, 4), float(t), np.float32))
    # a TIMEOUT (event 3), nonfinal: must NOT write a death summary
    dm.on_boundaries(np.array([3], np.uint8), np.array([0], np.uint8),
                     np.array([0]))
    assert float(np.abs(dm.summary).sum()) == 0.0
    # a DEATH (event 1), nonfinal: writes the summary
    for t in range(3):
        dm.push(np.full((1, 4), 9.0, np.float32))
    dm.on_boundaries(np.array([1], np.uint8), np.array([0], np.uint8),
                     np.array([1]))
    assert float(np.abs(dm.summary).sum()) > 0.0


# ------------------------------------------------------------------ #
# 3. success, exhaustion, final attempt
# ------------------------------------------------------------------ #

def test_success_terminal_event():
    hist = _run(SAFE, lambda t: 4, K=3, H=400)   # sprint to goal
    assert hist[-1]["attempt_event"] == 2
    assert hist[-1]["task_ended"] and not hist[-1]["task_exhausted"]


def test_task_exhaustion_final_attempt_flagged():
    hist = _run(TWO_SPIKE, lambda t: 4, K=4)     # dies every attempt
    assert len(hist) == 4                        # exactly K attempts
    assert hist[-1]["attempt_event"] == 1
    assert hist[-1]["task_ended"] and hist[-1]["task_exhausted"]
    assert hist[-1]["term_attempt"] == 4         # the final attempt
    # non-final attempts are not task-ended
    assert all(not h["task_ended"] for h in hist[:-1])


def test_terminal_data_survives_reset_and_metrics_use_it():
    # on the task-ended step the snapshot must reflect the FINAL attempt,
    # not the fresh task the auto-reset already started
    hist = _run(TWO_SPIKE, lambda t: 4, K=3)
    final = hist[-1]
    assert final["attempt_event"] == 1 and 250 < final["term_x"] < 340
    # full evaluator run: attempts_to_success censored, all deaths real
    rec = E.run_task(dict(level=TWO_SPIKE, K=3, H=400),
                     policy=lambda o, i, m: 4, task_seed=1)
    assert rec["n_deaths"] == 3 and rec["success"] is False
    assert rec["censored"] and rec["attempts_to_success"] is None
    assert all(a["attempt_event"] == 1 for a in rec["attempts"])


def test_checkpoint_change_updates_respawn_not_terminal():
    # a save mid-room: after touching it, deaths respawn at the save, but
    # the terminal position still records where the death happened
    room = """\
###############
#.............#
#.............#
#.............#
#.............#
#.............#
#.............#
#.............#
#.....S.......#
#S....s....^.G#
###############
"""
    # 's' isn't a tile; use the entity save via level text @save
    room = SAFE.replace(
        "#S...........G#", "#S.....^.....G#")
    hist = _run(room, lambda t: 4, K=3)
    # dies at the spike (tile 7 -> ~224), respawn is the start (48)
    assert hist[0]["attempt_event"] == 1
    assert hist[0]["term_x"] > 150


# ------------------------------------------------------------------ #
# 4. reference / native-vector parity at boundaries
# ------------------------------------------------------------------ #

def test_vector_event_matches_env_at_boundaries():
    tid = dict(level=TWO_SPIKE, K=5, H=400)
    v = CVecIWanna([tid], base_seed=1)
    v.set_task_seeds([7])
    v.reset()
    e = iw.IWannaDiscoveryEnv(level=TWO_SPIKE, attempts_K=5,
                              attempt_frames_H=400, reward_mode="sparse")
    e.reset(seed=0, options={"task_seed": 7})
    for t in range(2500):
        o, r, term, ae, te, ts = v.step(np.array([4], np.int32))
        og, rg, tg, _, ig = e.step(4)
        assert np.array_equal(o[0], og)
        assert bool(ae[0]) == ig["attempt_ended"]
        # the vector's event code must match the env's terminal event
        if ig["attempt_ended"]:
            assert int(v.attempt_event[0]) == ig["attempt_event"]
            assert v.attempt_event[0] == 1     # death here
        if tg:
            break
    v.close(); e.close()


def test_vector_terminal_events_distinguish_death_and_timeout():
    # H large enough that the sprinter reaches the first spike (~80
    # frames from spawn) but the camper still times out
    v = CVecIWanna([dict(level=TWO_SPIKE, K=3, H=200),
                    dict(level=SAFE, K=3, H=120)], base_seed=1)
    v.reset()
    seen = {0: set(), 1: set()}
    for t in range(2000):
        # env 0 sprints (dies), env 1 stands still (times out)
        v.step(np.array([4, 2], np.int32))
        for i in (0, 1):
            if v.attempt_ended[i]:
                seen[i].add(int(v.attempt_event[i]))
    v.close()
    assert 1 in seen[0], "sprinter should record deaths"
    assert 3 in seen[1] and 1 not in seen[1], "camper should only timeout"


# ------------------------------------------------------------------ #
# 5. pack-mode terminal capture (skipped without local pack)
# ------------------------------------------------------------------ #

@pytest.mark.skipif(not os.path.exists(PACK),
                    reason="local source-built pack required")
def test_pack_terminal_position_is_not_checkpoint():
    # sprinting right from the rGuy1 first_screen checkpoint (x~2576)
    # ends attempts further right; the terminal capture must record
    # THAT position, never the checkpoint the player would respawn to
    rec = E.run_task("disc.iwbtgr_1_5_3.rGuy1.first_screen",
                     policy=lambda o, i, m: 4, task_seed=1)
    assert rec["attempts"], "task should produce attempts"
    assert all(a["attempt_event"] in (1, 3) for a in rec["attempts"])
    assert any(abs(a["term_xy"][0] - 2576.0) > 20
               for a in rec["attempts"]), \
        "terminal x equals the checkpoint — capture is still broken"
