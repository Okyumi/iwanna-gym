"""Observation-matched informative-failure positive control (no RL).

This is the audited, headline replacement for the privileged control in
``probes.py`` (whose ``FailureMemoryAgent`` reads the evaluator-only
terminal snapshot ``term_x``/``term_room`` — see the leakage audit in
``docs/informative_failure_control.md``). Here EVERY agent conditions ONLY
on facts a headline policy actually observes:

  - the observation vector (``obs[0]`` = normalized player x, ``obs[5]`` =
    on-ground flag);
  - the permitted attempt-boundary flag (``input_protocol``): "a new
    attempt just began" — an OBSERVED fact (the agent was respawned);
  - whether the task ended in success (the episode terminated).

The death location an agent remembers is its OWN last observed x before an
attempt ended — NOT the exact terminal coordinate. On the informative
rooms (``scripts/make_informative_rooms.py``) the hidden trap is a spike
spawned by an INVISIBLE ``enter_region`` band: it is absent from the
observation until it kills, so the trap column is *initially ambiguous*
and can only be learned by dying there (an OBSERVABLE failure). The trap
column varies across rooms, so no fixed action sequence solves them all.

Four arms isolate what actually drives success:

  * ``obs_memory``   — jumps over the OBSERVED death column. Headline.
  * ``erased``       — same agent, memory cut each attempt (never jumps).
  * ``fixed``        — a single blind action program, same every attempt.
  * ``attempt_counter`` — jumps on attempt >= 2 exactly like obs_memory,
    but at a FIXED guessed column independent of the observed death — so a
    difference from obs_memory is attributable to the OBSERVED LOCATION,
    not to the attempt counter or to "trying a jump on a later attempt".

Reported per arm: success AND death/attempt COST (repeatability alone is
not evidence — a memory-erased twin also "reproducibly" fails).
"""
from __future__ import annotations

import glob
import json
import os

from iwanna_gym.env import IWannaDiscoveryEnv

#: standard controlled-room width in px (25 tiles * 32). Used only to read
#: the agent's own position out of obs[0]; it is a fixed screen constant,
#: not hidden task state.
ROOM_W = 25 * 32

#: full-held-jump avoidance parameters (validated in
#: docs/informative_failure_control.md): begin the jump LEAD px before the
#: target column and hold jump for JHOLD frames so the airborne arc covers
#: the trap band; re-jump after landing while still short of the target.
LEAD = 34.0
JHOLD = 11
A_RUN = 4        # right, no jump
A_JUMP = 5       # right, jump held


def _obs_x(obs) -> float:
    """Denormalize the player's x from the observation alone."""
    return (float(obs[0]) + 1.0) * ROOM_W / 2.0


def _on_ground(obs) -> bool:
    return float(obs[5]) > 0.5


class _JumpController:
    """Shared full-held-jump-over-a-column primitive (observation only)."""

    def __init__(self):
        self._jle = -999      # frame the current jump started
        self._frame = 0

    def step(self, obs, target_x, active: bool) -> int:
        self._frame += 1
        x = _obs_x(obs)
        if not active or target_x is None:
            return A_RUN
        # start a jump LEAD px before the target if grounded and short of it
        if (x >= target_x - LEAD and x < target_x
                and _on_ground(obs) and self._frame - self._jle > JHOLD):
            self._jle = self._frame
        if self._frame - self._jle < JHOLD:
            return A_JUMP
        return A_RUN


class ObsMemoryAgent:
    """Headline arm. Remembers the OWN-observed x where the last attempt
    failed and jumps over it next time. ``use_memory=False`` is the
    byte-identical memory-erased twin (records nothing -> never jumps)."""

    def __init__(self, use_memory: bool = True):
        self.use_memory = use_memory
        self.reset_task()

    def reset_task(self):
        self.death_x = None          # observed x of the most recent failure
        self._last_x = None
        self._jc = _JumpController()

    def observe_step(self, obs):
        self._last_x = _obs_x(obs)

    def on_boundary(self, success: bool):
        # record the OWN last observed position at any FAILED attempt end;
        # the erased twin records nothing
        if not success and self.use_memory and self._last_x is not None:
            self.death_x = self._last_x

    def act(self, obs) -> int:
        return self._jc.step(obs, self.death_x, active=self.death_x is not None)


class FixedScheduleAgent:
    """Blind control: one fixed action program, identical every attempt and
    every room. Jumps over a FIXED guessed column; no observation of the
    death location, no per-attempt change. A single sequence cannot clear
    rooms whose trap sits elsewhere."""

    def __init__(self, guess_x: float = ROOM_W / 2.0):
        self.guess_x = guess_x
        self.reset_task()

    def reset_task(self):
        self._jc = _JumpController()

    def observe_step(self, obs):
        pass

    def on_boundary(self, success: bool):
        pass

    def act(self, obs) -> int:
        return self._jc.step(obs, self.guess_x, active=True)


class AttemptCounterAgent:
    """Attempt-counter control: jumps on attempt >= 2 exactly like the
    memory agent, but at a FIXED guessed column INDEPENDENT of the observed
    death. Isolates the value of the observed LOCATION from the value of
    the attempt counter ("try a jump on a later attempt")."""

    def __init__(self, guess_x: float = ROOM_W / 2.0):
        self.guess_x = guess_x
        self.reset_task()
        self.attempt = 0

    def reset_task(self):
        self._jc = _JumpController()

    def observe_step(self, obs):
        pass

    def on_boundary(self, success: bool):
        self.attempt += 1

    def act(self, obs) -> int:
        return self._jc.step(obs, self.guess_x, active=self.attempt >= 1)


def run_arm(level: str, agent, K: int = 25, H: int = 400) -> dict:
    """Run one scripted agent on one informative room; returns success and
    death/attempt cost. Pure observation-driven replay."""
    env = IWannaDiscoveryEnv(level=level, obs_mode="observable_vector",
                             attempts_K=K, attempt_frames_H=H,
                             reward_mode="sparse")
    obs, info = env.reset(seed=0, options={"task_seed": 1})
    if hasattr(agent, "reset_task"):
        agent.reset_task()
    success = False
    deaths = 0
    attempts_used = 1
    max_frames = K * H + K + 4
    for _ in range(max_frames):
        agent.observe_step(obs)
        a = agent.act(obs)
        obs, r, term, tru, info = env.step(int(a))
        if info["attempt_ended"]:
            succ = info["attempt_event"] in (2, 4)
            if info["attempt_event"] == 1:
                deaths += 1
            agent.on_boundary(succ)
            attempts_used = info["term_attempt"]
            if succ:
                success = True
        if term:
            break
    env.close()
    return {"success": success, "deaths": deaths,
            "attempts_used": attempts_used}


def informative_control(level: str, K: int = 25, H: int = 400) -> dict:
    """All four arms on one informative room."""
    return {
        "level": level,
        "obs_memory": run_arm(level, ObsMemoryAgent(True), K, H),
        "erased": run_arm(level, ObsMemoryAgent(False), K, H),
        "fixed": run_arm(level, FixedScheduleAgent(), K, H),
        "attempt_counter": run_arm(level, AttemptCounterAgent(), K, H),
    }


def informative_rooms() -> list[str]:
    """Registered informative-room level names, sorted."""
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "levels", "informative")
    names = sorted(os.path.splitext(os.path.basename(p))[0]
                   for p in glob.glob(os.path.join(d, "*.txt")))
    return [f"informative/{n}" for n in names]


def informative_suite(K: int = 25, H: int = 400) -> dict:
    """Run the four-arm control over every informative room and summarize.

    ``separates`` requires: obs_memory solves, the erased twin does NOT,
    and neither blind control (fixed / attempt_counter) solves — i.e. the
    OBSERVED death location is what makes the difference, not memorization
    or the attempt counter."""
    rooms = informative_rooms()
    rows = [informative_control(lv, K, H) for lv in rooms]
    def solved(arm):
        return sum(1 for r in rows if r[arm]["success"])
    def mean_deaths_to_success(arm):
        ds = [r[arm]["deaths"] for r in rows if r[arm]["success"]]
        return (sum(ds) / len(ds)) if ds else None
    summary = {
        "n_rooms": len(rows),
        "solved": {a: solved(a) for a in
                   ("obs_memory", "erased", "fixed", "attempt_counter")},
        "mean_deaths_to_success": {
            a: mean_deaths_to_success(a) for a in
            ("obs_memory", "erased", "fixed", "attempt_counter")},
        "separates": [
            r["level"] for r in rows
            if r["obs_memory"]["success"] and not r["erased"]["success"]
            and not r["fixed"]["success"] and not r["attempt_counter"]["success"]
        ],
        "rows": rows,
    }
    return summary


def main(out: str = "build/informative_control/results.json"):
    s = informative_suite()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(s, f, indent=2)
    print(json.dumps({k: v for k, v in s.items() if k != "rows"}, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
