"""PRIVILEGED (oracle) failure-memory probe — no RL, no training.

NOTE (leakage audit, docs/informative_failure_control.md): this agent
reads the exact terminal-event snapshot ``term_x``/``term_room`` — an
EVALUATOR-FACING interface that is NOT part of the policy observation
vector (which carries only a normalized player position, ~one frame
stale, and no room index). Because the exact terminal coordinate is
slightly more precise than anything an observation-only policy sees, this
agent is a PRIVILEGED UPPER BOUND, not the headline positive control. Its
tasks (the t01..t20 rooms) also use VISIBLE hazards, so their hidden state
is not "initially ambiguous". The headline, observation-matched control —
which conditions only on the agent's OWN observations and runs on rooms
whose trap is invisible until it kills — lives in
``iwanna_gym/discovery/informative.py``.

This module is retained as the labeled oracle bound and for reproducing
the earlier privileged-probe numbers. A deterministic agent conditioning
on the exact death position solves 9/14 active controlled tasks within K
attempts while its memory-erased twin fails all attempts; that shows an
agent WITH privileged failure coordinates can exploit them — a strictly
weaker claim than the observation-matched control, which is why the
headline result is the latter.
"""
from __future__ import annotations

from . import registry as R


class FailureMemoryAgent:
    """Scripted agent conditioning on observed death history only."""

    #: maneuvers tried, in order, when nearing a remembered death x
    MANEUVERS = ("brake", "hop", "wait", "leap", "double")

    def __init__(self, use_memory: bool = True, brake_margin: float = 60.0):
        self.use_memory = use_memory
        self.brake_margin = brake_margin
        self.reset_task()

    def reset_task(self):
        self.deaths: list[tuple[float, int]] = []   # (x, room)
        self._attempt_deaths_seen = 0

    def observe(self, info):
        if info.get("attempt_ended") and info.get("attempt_event") == 1:
            if self.use_memory:
                self.deaths.append((info["term_x"], info["term_room"]))
            # a memory-erased twin records nothing across attempts

    def _maneuver_for(self, attempt_index: int) -> str:
        # cycle the maneuver deterministically with each death so the
        # agent "tries something different" after repeated failure
        return self.MANEUVERS[attempt_index % len(self.MANEUVERS)]

    def act(self, obs, info, room, x, phase):
        # danger = an observed death in THIS room just ahead of us
        near = None
        for (dx, droom) in self.deaths:
            if droom == room and 0 <= dx - x <= self.brake_margin:
                near = dx
                break
        if near is None:
            return 4                       # sprint right
        man = self._maneuver_for(len(self.deaths))
        # `phase` is a per-attempt frame counter used to sequence a
        # multi-frame maneuver deterministically
        if man == "brake":
            return 2 if phase % 6 < 4 else 4
        if man == "hop":
            return 5 if phase % 18 < 6 else 4
        if man == "wait":
            return 2 if phase < 40 else 4
        if man == "leap":
            return 5 if phase % 40 < 16 else 4
        if man == "double":
            return 5 if (phase % 44) < 16 or 20 <= (phase % 44) < 34 else 4
        return 4


def run_control(task, use_memory: bool, task_seed: int = 1,
                obs_mode: str = "observable_vector",
                registry=None) -> dict:
    """Run the scripted agent (memory on/off) on one task; returns a
    summary with success and per-attempt death record. Pure replay."""
    from iwanna_gym.discovery.evaluator import _make_env
    reg = registry if registry is not None else R.load_registry()
    env, meta = _make_env(task, obs_mode, reg)
    agent = FailureMemoryAgent(use_memory=use_memory)
    obs, info = env.reset(seed=0, options={"task_seed": task_seed})
    agent.reset_task()
    K = meta["attempts_K"]
    total = K * meta["attempt_frames_H"] + K + 2
    phase = 0
    deaths = []
    success = False
    attempts_used = 1
    for _ in range(total):
        a = agent.act(obs, info, info["room"], info["x"], phase)
        obs, r, term, tru, info = env.step(int(a))
        phase += 1
        agent.observe(info)
        if info["attempt_ended"]:
            phase = 0
            if info["attempt_event"] in (2, 4):
                success = True
            elif info["attempt_event"] == 1:
                deaths.append([round(info["term_x"], 1),
                               round(info["term_y"], 1),
                               int(info["term_room"])])
            attempts_used = info["term_attempt"]
        if term:
            break
    env.close()
    return {"task_id": meta["task_id"], "use_memory": use_memory,
            "task_seed": task_seed, "success": success,
            "attempts_used": attempts_used, "n_deaths": len(deaths),
            "deaths": deaths}


def positive_control(task, task_seed: int = 1, registry=None) -> dict:
    """Paired memory-on vs memory-erased run on one task+seed."""
    reg = registry if registry is not None else R.load_registry()
    mem = run_control(task, True, task_seed, registry=reg)
    blind = run_control(task, False, task_seed, registry=reg)
    return {
        "task": mem["task_id"], "task_seed": task_seed,
        "memory": {"success": mem["success"],
                   "attempts_used": mem["attempts_used"],
                   "n_deaths": mem["n_deaths"]},
        "memory_erased": {"success": blind["success"],
                          "attempts_used": blind["attempts_used"],
                          "n_deaths": blind["n_deaths"]},
        # the positive-control signal: memory solves it, erased does not
        "separates": bool(mem["success"] and not blind["success"]),
    }
