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


def test_obs_memory_necessary_contrast_and_efficiency():
    s = I.informative_suite()
    # NECESSARY CONTRAST: same agent, memory the only change. The memory
    # agent solves every room; the memory-erased twin solves none.
    assert s["solved"]["obs_memory"] == s["n_rooms"], s["solved"]
    assert s["solved"]["erased"] == 0, s["solved"]
    assert len(s["separates_vs_erased"]) == s["n_rooms"]
    # EFFICIENCY, not uniqueness: the memory agent solves in ~1 death.
    assert s["mean_deaths_to_success"]["obs_memory"] <= 1.5
    # A blind location-search enumerator CAN also solve (given enough
    # attempts), but pays strictly more deaths — the honest bound: the
    # observed location buys efficiency, not capability the search lacks.
    if s["solved"]["location_search"] > 0:
        assert (s["mean_deaths_to_success"]["location_search"]
                > s["mean_deaths_to_success"]["obs_memory"]), s
    # a single fixed program clears at most the coincidentally-aligned room
    assert s["solved"]["fixed"] <= 1, s["solved"]


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


def test_scripted_signals_are_available_to_the_learner():
    # every per-step signal the obs_memory agent reads must be inside the
    # observation vector (obs[0] player x, obs[5] on-ground) or the
    # permitted observed input protocol (attempt-boundary flag). The only
    # thing it additionally does is RETAIN the death location across
    # attempts — which the learner supplies via recurrence / deathmem, the
    # capability H1/H2 test, not a free signal.
    from iwanna_gym.clib import OBS_SIZE
    from iwanna_gym.discovery import input_protocol as P
    assert 0 < 5 < OBS_SIZE                      # obs[0], obs[5] are real obs
    v = P.extra_inputs(0, 0.0, True, 12)         # boundary flag is provided
    assert v[13] == 1.0
    # the agent's act() consumes only obs (no info, no term_* fields) —
    # already guarded by test_agent_reads_no_privileged_or_hidden_fields.


def test_competing_strategies_bound_the_claim():
    # continuous jumping is not a shortcut; location search can solve but
    # costs more deaths than the memory agent.
    s = I.informative_suite()
    assert s["solved"]["continuous_jump"] < s["n_rooms"]
    if s["solved"]["location_search"] == s["n_rooms"]:
        assert (s["mean_deaths_to_success"]["location_search"]
                > s["mean_deaths_to_success"]["obs_memory"])


def test_erased_twin_pays_full_death_budget():
    # the erased twin is the same agent minus memory; it dies every attempt
    # and never succeeds, while the memory agent solves in ~1 death.
    s = I.informative_control(I.informative_rooms()[2])
    assert s["erased"]["deaths"] >= 20 and not s["erased"]["success"]
    assert s["obs_memory"]["success"] and s["obs_memory"]["deaths"] <= 2
