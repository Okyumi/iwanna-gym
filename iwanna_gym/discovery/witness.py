"""Completion witnesses for discovery tasks.

A witness is a committed, metadata-only record proving a task is
completable: a concrete action sequence that, replayed from a pinned
task seed, reaches the task's success condition within the budget. Two
independent sources produce them:

  - controlled rooms: the scripted rule probes of
    ``scripts/probe_traps.py`` (state-reactive policies a careful human
    would follow), with the emitted action sequence recorded;
  - native tasks: a deterministic macro beam search over the real
    environment (replay-based — the engine's bit-exact determinism is
    the search's only crutch; no privileged state is written into the
    witness, only the action integers that solve the task).

Every witness is VALIDATED by replay through the standard observable
discovery env before being written; ``verify_witness`` re-checks a
committed witness at test time.
"""
from __future__ import annotations

import json
import os
import time

from . import registry as R

WITNESS_FORMAT = "discovery-witness/1"


def _run_actions(spec: R.TaskSpec, actions, task_seed: int):
    """Replay actions in the standard observable env; returns final
    info-like summary (success, frames, deaths)."""
    env = R.make_env(spec.task_id, obs_mode="observable_vector")
    env.reset(seed=0, options={"task_seed": task_seed})
    success, frames, term = False, 0, False
    info = {}
    for a in actions:
        obs, r, term, tr, info = env.step(int(a))
        frames += 1
        if term:
            success = bool(info["task_success"])
            break
    deaths = (info.get("final_task_deaths") if term
              else info.get("death_count", 0))
    env.close()
    return success, frames, int(deaths or 0)


def verify_witness(spec: R.TaskSpec, witness: dict) -> bool:
    ok, frames, deaths = _run_actions(spec, witness["actions"],
                                      witness["task_seed"])
    return ok


def write_witness(spec: R.TaskSpec, actions, task_seed: int,
                  source: str) -> dict:
    ok, frames, deaths = _run_actions(spec, actions, task_seed)
    if not ok:
        raise ValueError(f"{spec.task_id}: witness replay failed")
    rec = {
        "format": WITNESS_FORMAT,
        "task_id": spec.task_id,
        "suite": spec.suite,
        "task_seed": task_seed,
        "actions": [int(a) for a in actions],
        "frames": frames,
        "deaths_before_success": deaths,
        "source": source,
        "note": "action integers only — metadata-safe to commit",
    }
    os.makedirs(R.WITNESS_DIR, exist_ok=True)
    with open(os.path.join(R.WITNESS_DIR, spec.task_id + ".json"), "w",
              encoding="utf-8") as f:
        json.dump(rec, f)
    return rec


# ------------------------------------------------------------------ #
# controlled rooms: record the scripted probes
# ------------------------------------------------------------------ #

def probe_witness(spec: R.TaskSpec, task_seed: int = 1) -> dict:
    """Drive the task's scripted probe INSIDE the discovery env and
    record the action sequence it emits."""
    assert spec.suite == "controlled"
    import importlib.util
    p = os.path.join("scripts", "probe_traps.py")
    mod_spec = importlib.util.spec_from_file_location("probe_traps", p)
    probes = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(probes)
    room = spec.room.split("/", 1)[1]
    fn = probes.PROBES[room]

    env = R.make_env(spec.task_id, obs_mode="observable_vector")
    env.reset(seed=0, options={"task_seed": task_seed})
    acts = []
    done = False
    for a in fn(env):
        obs, r, done, tr, info = env.step(int(a))
        acts.append(int(a))
        if done:
            break
    if not done:
        for _ in range(120):
            obs, r, done, tr, info = env.step(2)
            acts.append(2)
            if done:
                break
    ok = done and bool(info["task_success"])
    env.close()
    if not ok:
        raise ValueError(f"{spec.task_id}: probe did not complete the task")
    return write_witness(spec, acts, task_seed, source="scripted_probe")


# ------------------------------------------------------------------ #
# native tasks: deterministic macro beam search
# ------------------------------------------------------------------ #

def _macros(n_actions: int):
    R4, L, IDLE = 4, 0, 2
    JR, JL, JI = 5, 1, 3
    mac = [
        [R4] * 6, [R4] * 16, [R4] * 32, [R4] * 64,
        [L] * 6, [L] * 16, [L] * 32,
        [IDLE] * 8, [IDLE] * 24, [IDLE] * 60,
        [JR] * 4 + [R4] * 3, [JR] * 10 + [R4] * 4, [JR] * 20 + [R4] * 6,
        [JL] * 4 + [L] * 3, [JL] * 10 + [L] * 4, [JL] * 20 + [L] * 6,
        [JR] * 16 + [R4] * 3 + [JR] * 14 + [R4] * 4,   # double jump R
        [JL] * 16 + [L] * 3 + [JL] * 14 + [L] * 4,     # double jump L
        [JI] * 18 + [IDLE] * 4, [JI] * 6 + [IDLE] * 3, # neutral jumps
        [JR] * 20 + [JI] * 10 + [R4] * 4,              # high arc right
        [R4] * 8 + [JR] * 18 + [R4] * 8,               # running leap R
        [L] * 8 + [JL] * 18 + [L] * 8,                 # running leap L
    ]
    if n_actions >= 12:
        mac.append([10] * 2 + [R4] * 4)                # shoot right
        mac.append([6] * 2 + [L] * 4)                  # shoot left
    return mac


def beam_search_witness(spec: R.TaskSpec, task_seed: int = 1,
                        beam: int = 20, depth: int = 48,
                        time_budget_s: float = 150.0) -> dict | None:
    """Deterministic replay-based beam search for a zero-death action
    sequence reaching the task goal. Returns the witness record or None
    (task stays pending_witness). Search state is reconstructed purely
    by replaying action prefixes — determinism is asserted elsewhere."""
    env = R.make_env(spec.task_id, obs_mode="observable_vector")
    macros = _macros(env.action_space.n)
    gx0, gy0, gx1, gy1 = spec.goal_rect
    gcx, gcy = (gx0 + gx1) / 2, (gy0 + gy1) / 2

    def rollout(prefix):
        """Replay prefix; returns (score, done, alive, x, y)."""
        env.reset(seed=0, options={"task_seed": task_seed})
        term = False
        info = {}
        for a in prefix:
            obs, r, term, tr, info = env.step(int(a))
            if term or info["attempt_ended"]:
                break
        if not info:
            return -1e18, False, True, 0.0, 0.0
        if info.get("attempt_ended") and not info.get("task_success"):
            return -1e18, False, False, info["x"], info["y"]   # died
        done = bool(term and info.get("task_success"))
        x, y = info["x"], info["y"]
        score = -abs(gcx - x) - abs(gcy - y)
        return score, done, True, x, y

    t0 = time.monotonic()
    frontier: list[tuple[float, list[int]]] = [(0.0, [])]
    for _ in range(depth):
        if time.monotonic() - t0 > time_budget_s:
            break
        cand: list[tuple[float, list[int]]] = []
        seen: set[tuple[int, int, int]] = set()
        for _, prefix in frontier:
            for mac in macros:
                if time.monotonic() - t0 > time_budget_s:
                    break
                seq = prefix + mac
                if len(seq) > spec.attempt_frames_H:
                    continue
                score, done, alive, x, y = rollout(seq)
                if done:
                    env.close()
                    return write_witness(spec, seq, task_seed,
                                         source="macro_beam_search")
                if not alive:
                    continue
                key = (int(x) // 8, int(y) // 8, len(seq) // 64)
                if key in seen:
                    continue
                seen.add(key)
                cand.append((score, seq))
        if not cand:
            break
        cand.sort(key=lambda t: -t[0])
        frontier = cand[:beam]
    env.close()
    return None
