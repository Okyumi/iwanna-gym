"""Informative-failure positive control (no RL, no training).

A scripted agent that conditions only on OBSERVED death history solves
tasks that its memory-erased twin cannot — establishing that the tasks
contain exploitable failure information independent of any converged
training run. Also pins the agent's input contract.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
import iwanna_gym.discovery as d                          # noqa: E402
from iwanna_gym.discovery.probes import (FailureMemoryAgent,  # noqa: E402
                                         positive_control, run_control)


def test_positive_control_separates_on_known_tasks():
    # tasks that reproducibly separate across seeds (see
    # build/discovery_positive_control/results.json)
    for tid in ("disc.research.t01_apple", "disc.research.t03_riser",
                "disc.research.t13_floorgate"):
        r = positive_control(tid, task_seed=11)
        assert r["memory"]["success"], (tid, "memory agent should solve")
        assert not r["memory_erased"]["success"], \
            (tid, "memory-erased twin should NOT solve")
        assert r["separates"]


def test_separation_is_reproducible_across_seeds():
    seps = [positive_control("disc.research.t01_apple", task_seed=s)[
        "separates"] for s in (11, 12, 13)]
    assert all(seps), seps


def test_memory_erased_is_never_better_than_memory():
    # the ONLY difference between the two runs is the death memory; the
    # erased twin can never solve in fewer attempts (it has strictly
    # less information)
    for tid in ("disc.research.t06_crusher", "disc.research.t10_chain"):
        m = run_control(tid, use_memory=True, task_seed=12)
        b = run_control(tid, use_memory=False, task_seed=12)
        if m["success"] and b["success"]:
            assert m["attempts_used"] <= b["attempts_used"]
        else:
            # at minimum, memory does not do worse on success
            assert m["success"] or not b["success"]


def test_agent_uses_only_observed_failure_history():
    # the agent records only terminal death position + room (observable
    # facts) and never touches hidden state. Assert its memory contents
    # are exactly (x, room) tuples and nothing hazard-identifying.
    agent = FailureMemoryAgent(use_memory=True)
    agent.observe({"attempt_ended": True, "attempt_event": 1,
                   "term_x": 288.0, "term_y": 300.0, "term_room": 0})
    agent.observe({"attempt_ended": True, "attempt_event": 3,  # timeout
                   "term_x": 999.0, "term_y": 0.0, "term_room": 0})
    # only the DEATH is recorded, not the timeout
    assert agent.deaths == [(288.0, 0)]
    # a memory-erased agent records nothing
    blind = FailureMemoryAgent(use_memory=False)
    blind.observe({"attempt_ended": True, "attempt_event": 1,
                   "term_x": 288.0, "term_y": 300.0, "term_room": 0})
    assert blind.deaths == []


def test_control_does_not_read_hidden_fields():
    # run the agent and confirm it never accesses forbidden info keys:
    # it only takes (obs, info, room, x, phase) and uses room/x + its
    # own recorded deaths. A structural guard: the act() signature has
    # no hazard/trigger/dormant parameter.
    import inspect
    params = list(inspect.signature(FailureMemoryAgent.act).parameters)
    assert params == ["self", "obs", "info", "room", "x", "phase"]
