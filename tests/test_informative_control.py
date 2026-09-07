"""Observation-matched informative-failure positive control (no RL).

Asserts the audited control: an agent conditioning only on its OWN observed
failure location solves the ambiguous-hidden-state rooms that its
memory-erased twin cannot, while blind (fixed-schedule) and attempt-counter
controls do NOT — so the OBSERVED death location is what drives success,
not memorization or the attempt counter. Also pins the agent's input
contract: it reads only obs[0]/obs[5] and the success/boundary flag, never
the evaluator-only terminal snapshot (term_x/term_room) or any hidden field.
"""
from __future__ import annotations

import inspect
import sys

sys.path.insert(0, ".")
import numpy as np                                          # noqa: E402
from iwanna_gym.discovery import informative as I           # noqa: E402


def test_rooms_exist_and_are_multiple_configs():
    rooms = I.informative_rooms()
    assert len(rooms) >= 6, rooms
    # distinct configurations (distinct trap columns), not one room repeated
    assert len(set(rooms)) == len(rooms)


def test_obs_memory_separates_from_erased_and_blind():
    s = I.informative_suite()
    # the observation-matched memory agent solves every room ...
    assert s["solved"]["obs_memory"] == s["n_rooms"], s["solved"]
    # ... in ~1 death (localizes the trap from its own observed failure)
    assert s["mean_deaths_to_success"]["obs_memory"] <= 1.5
    # the memory-erased twin never solves
    assert s["solved"]["erased"] == 0, s["solved"]
    # a single fixed program / attempt counter clears at most the room whose
    # trap coincides with its fixed guess (here the center), never all
    assert s["solved"]["fixed"] <= 1, s["solved"]
    assert s["solved"]["attempt_counter"] <= 1, s["solved"]
    # most rooms separate cleanly (memory solves; erased & both blind fail)
    assert len(s["separates"]) >= s["n_rooms"] - 1, s["separates"]


def test_control_is_seed_invariant_deterministic():
    # the rooms are fully deterministic: task_seed does not change the
    # hidden state, so "N seeds" is one configuration N times. Distinct
    # rooms are the distinct configurations.
    lvl = I.informative_rooms()[2]
    outs = [I.run_arm(lvl, I.ObsMemoryAgent(True)) for _ in range(3)]
    assert all(o == outs[0] for o in outs), outs
    outs_seedvary = []
    for seed in (1, 7, 42):
        env = __import__("iwanna_gym.env", fromlist=["IWannaDiscoveryEnv"]) \
            .IWannaDiscoveryEnv(level=lvl, obs_mode="observable_vector",
                                attempts_K=25, attempt_frames_H=400,
                                reward_mode="sparse")
        obs, info = env.reset(seed=0, options={"task_seed": seed})
        ag = I.ObsMemoryAgent(True)
        succ = False
        for _ in range(25 * 400 + 30):
            ag.observe_step(obs)
            obs, r, term, tru, info = env.step(int(ag.act(obs)))
            if info["attempt_ended"]:
                ag.on_boundary(info["attempt_event"] in (2, 4))
                if info["attempt_event"] in (2, 4):
                    succ = True
            if term:
                break
        env.close()
        outs_seedvary.append(succ)
    assert all(outs_seedvary), outs_seedvary


def test_trap_is_invisible_in_observation_until_death():
    # on the approach the observable entity block is empty: the trap is
    # absent from the observation, so the trap column is not derivable a
    # priori (initially ambiguous hidden state).
    from iwanna_gym.env import IWannaDiscoveryEnv
    lvl = I.informative_rooms()[2]
    env = IWannaDiscoveryEnv(level=lvl, obs_mode="observable_vector",
                             attempts_K=1, attempt_frames_H=400,
                             reward_mode="sparse")
    obs, info = env.reset(seed=0, options={"task_seed": 1})
    ent_base = obs.shape[0] - I.__dict__.get("_ENT_SLOTS", 6 * 5)
    for _ in range(20):                    # first ~20 frames of the approach
        assert np.count_nonzero(obs[ent_base:]) == 0, "hazard visible early"
        obs, r, term, tru, info = env.step(I.A_RUN)
        if info["attempt_ended"]:
            break
    env.close()


def test_agent_reads_no_privileged_or_hidden_fields():
    # act() takes only the observation; on_boundary takes only a success
    # bool. No info dict, no term_x/term_room, no hazard/task parameters.
    assert list(inspect.signature(I.ObsMemoryAgent.act).parameters) == \
        ["self", "obs"]
    assert list(inspect.signature(I.ObsMemoryAgent.on_boundary).parameters) == \
        ["self", "success"]
    # source-level guard: the AGENTS never touch info at all — only the
    # harness (run_arm, standing in for the evaluator) reads info to compute
    # the plain success/death bool it hands the agent. Scan every agent +
    # helper, not the harness.
    for obj in (I.ObsMemoryAgent, I.FixedScheduleAgent, I.AttemptCounterAgent,
                I._JumpController, I._obs_x, I._on_ground):
        src = inspect.getsource(obj)
        for forbidden in ("term_x", "term_y", "term_room", "attempt_event",
                          "info", "hazard", "dormant"):
            assert forbidden not in src, (obj.__name__, forbidden)


def test_erased_twin_pays_full_death_budget():
    # the erased twin is the same agent minus memory; it dies every attempt
    # and never succeeds, while the memory agent solves in ~1 death.
    s = I.informative_control(I.informative_rooms()[2])
    assert s["erased"]["deaths"] >= 20 and not s["erased"]["success"]
    assert s["obs_memory"]["success"] and s["obs_memory"]["deaths"] <= 2
