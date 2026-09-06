"""Library-independent evaluator for the discovery benchmark.

Drives any policy — a callable ``policy(obs, info, memory) -> action``
plus a memory object with ``reset_task()`` — through registry tasks and
records, per task and per attempt: outcome, attempt length, total
frames, death location and trajectory index, progress-to-goal. From
those records it computes the contract's metrics (section 6):
success-by-attempt curve and AUC, attempts/frames to first success,
repeated-death rate, post-discovery improvement, and per-split transfer
numbers. No RL library is imported anywhere here.

The evaluator — not the policy — owns every diagnostic quantity; the
policy sees only its observation. Memory protocol enforcement is
explicit: ``memory.reset_task()`` is called exactly at task boundaries
and never at attempt boundaries.

Aggregation rule (contract section 6 / milestone item 8): one task run
contributes ONE sample per metric. Frames within a trajectory are never
treated as independent samples; uncertainty is the standard error over
task runs (tasks x seeds).

Memory-oracle diagnostic (upper bound only): ``oracle=True`` runs the
policy with the PRIVILEGED observation vector and hands its memory the
per-attempt death log plus the env's entity dump. Oracle records are
tagged ``oracle: true``, written to ``*.oracle.jsonl``, and
``aggregate()`` refuses to mix them with standard records — they are
never part of the policy-facing benchmark.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Callable

from . import registry as R

RDR_RADIUS_PX = 32.0
# v2: per-attempt records carry the terminal-event snapshot (attempt_event,
# term_xy, term_room) captured before respawn. v1 records (the pre-repair
# pilot) stored checkpoint coordinates as death_xy and are NOT comparable.
RESULT_FORMAT = "discovery-eval/2"


class NullMemory:
    """Memoryless baseline: the reference memory object."""

    def reset_task(self) -> None:
        pass

    def observe(self, info: dict) -> None:
        pass


def run_task(task,
             policy: Callable[[Any, dict, Any], int],
             memory=None,
             task_seed: int = 1,
             obs_mode: str = "observable_vector",
             oracle: bool = False,
             registry: dict[str, R.TaskSpec] | None = None) -> dict:
    """One full task (K attempts or success); returns the task record.
    `task` is a registry task id (str) or a raw task spec dict
    ({level|game+room, K, H, suite, split})."""
    reg = registry if registry is not None else R.load_registry()
    if oracle:
        obs_mode = "privileged_vector"
    memory = memory if memory is not None else NullMemory()
    env, meta = _make_env(task, obs_mode, reg)
    K = meta["attempts_K"]
    obs, info = env.reset(seed=0, options={"task_seed": task_seed})
    memory.reset_task()                       # the ONLY memory reset

    gcx, gcy = _goal_center(meta, info)
    d0 = abs(gcx - info["x"]) + abs(gcy - info["y"])

    attempts: list[dict] = []
    cur = {"frames": 0, "min_goal_dist": d0}
    env_frame = 0                             # real trajectory index
    total = K * meta["attempt_frames_H"]
    if oracle:
        # upper-bound diagnostic: privileged hazard memory
        memory.oracle_entities = env.c.entities().tolist()
        memory.oracle_deaths = []

    while env_frame < total + K + 2:
        a = policy(obs, info, memory)
        obs, r, term, trunc, info = env.step(int(a))
        env_frame += 1
        cur["frames"] += 1
        if info["attempt_ended"]:
            # on the boundary step info["x"]/["y"] is the RESPAWN point;
            # the terminal position lives in the terminal-event snapshot
            px, py = info["term_x"], info["term_y"]
        else:
            px, py = info["x"], info["y"]
        d = abs(gcx - px) + abs(gcy - py)
        cur["min_goal_dist"] = min(cur["min_goal_dist"], d)
        memory.observe(info)
        if info["attempt_ended"]:
            ev = info["attempt_event"]        # 1 death 2 succ 3 timeout 4 complete
            outcome = {1: "death", 2: "success", 3: "timeout",
                       4: "success"}[ev]
            term_dist = abs(gcx - px) + abs(gcy - py)
            rec = {
                "outcome": outcome,
                "attempt_event": ev,
                "frames": cur["frames"],
                "traj_index": env_frame,      # real cumulative env frame
                "term_xy": [px, py],
                "term_room": info["term_room"],
                "min_goal_dist": cur["min_goal_dist"],
                "term_goal_dist": term_dist,
                "progress": 1.0 - cur["min_goal_dist"] / max(d0, 1e-9),
                "task_exhausted": bool(info.get("task_exhausted")),
            }
            if outcome == "death":            # death-only bookkeeping
                if oracle:
                    memory.oracle_deaths.append(rec["term_xy"])
            attempts.append(rec)
            cur = {"frames": 0, "min_goal_dist": d0}
        if term:
            break
    env.close()

    return {
        "format": RESULT_FORMAT,
        "suite_version": R.SUITE_VERSION,
        "task_id": meta["task_id"],
        "suite": meta["suite"],
        "split": meta["split"],
        "task_seed": task_seed,
        "obs_mode": obs_mode,
        "oracle": bool(oracle),
        "attempts_K": K,
        "attempts": attempts,
        **task_metrics(attempts, K),
    }


def _make_env(task, obs_mode: str, reg):
    """Build a discovery env for either a registry task id or a raw task
    spec dict ({level|game/room, K, H}); return (env, meta)."""
    from iwanna_gym.env import IWannaDiscoveryEnv
    if isinstance(task, str):
        spec = reg[task]
        env = R.make_env(task, obs_mode=obs_mode, registry=reg)
        return env, {"task_id": spec.task_id, "suite": spec.suite,
                     "split": spec.split, "attempts_K": spec.attempts_K,
                     "attempt_frames_H": spec.attempt_frames_H,
                     "goal_rect": spec.goal_rect}
    t = dict(task)
    K = int(t.get("K", 25))
    H = int(t.get("H", 2000))
    if "level" in t:
        env = IWannaDiscoveryEnv(level=t["level"], obs_mode=obs_mode,
                                 attempts_K=K, attempt_frames_H=H,
                                 reward_mode="sparse")
        tid = t.get("task_id", t["level"])
    else:
        env = IWannaDiscoveryEnv(game=t["game"], mode="room",
                                 room_id=t["room"], obs_mode=obs_mode,
                                 attempts_K=K, attempt_frames_H=H,
                                 reward_mode="sparse")
        tid = t.get("task_id", f"{t['game']}:{t['room']}")
    return env, {"task_id": tid, "suite": t.get("suite", "raw"),
                 "split": t.get("split", "n/a"), "attempts_K": K,
                 "attempt_frames_H": H, "goal_rect": None}


def _goal_center(meta, info):
    gr = meta.get("goal_rect")
    if gr:
        return (gr[0] + gr[2]) / 2, (gr[1] + gr[3]) / 2
    return info["goal"]


# ------------------------------------------------------------------ #
# per-task metric computation (pure functions; unit-tested)
# ------------------------------------------------------------------ #

def task_metrics(attempts: list[dict], K: int) -> dict:
    succ_at = next((i + 1 for i, a in enumerate(attempts)
                    if a["outcome"] == "success"), None)
    frames_cum = 0
    frames_to_success = None
    for a in attempts:
        frames_cum += a["frames"]
        if a["outcome"] == "success":
            frames_to_success = frames_cum
            break
    deaths = [a for a in attempts if a["outcome"] == "death"]
    # Repeated-death rate (a documented PROXY, not proof of informative
    # failure): a death after the first counts as "repeated" iff an
    # earlier death in this task occurred in the SAME ROOM within
    # RDR_RADIUS_PX of it. Coordinates from different rooms share a
    # coordinate frame in the source but are different places, so room
    # id gates the proximity test — spatial proximity alone would
    # conflate them. Proximity is a spatial proxy for "the same hazard",
    # not a hazard-identity check; true hazard identity would require
    # the simulator-only attribution the anti-leakage contract keeps out
    # of policy inputs (available to this evaluator, future work).
    repeated = 0
    for i, dcur in enumerate(deaths[1:], start=1):
        x, y = dcur["term_xy"]
        room = dcur.get("term_room")
        if any(p.get("term_room") == room and
               math.hypot(x - p["term_xy"][0], y - p["term_xy"][1])
               <= RDR_RADIUS_PX for p in deaths[:i]):
            repeated += 1
    rdr = repeated / max(len(deaths) - 1, 1) if len(deaths) > 1 else None
    # post-discovery improvement: progress gained after the first
    # failure, relative to attempt 1
    pdi = None
    if len(attempts) > 1 and attempts[0]["outcome"] != "success":
        later = max(a["progress"] for a in attempts[1:])
        pdi = later - attempts[0]["progress"]
    return {
        "success": succ_at is not None,
        "attempts_to_success": succ_at,           # None = censored at K
        "frames_to_success": frames_to_success,
        "n_attempts": len(attempts),
        "n_deaths": len(deaths),
        "repeated_death_rate": rdr,
        "post_discovery_improvement": pdi,
        "censored": succ_at is None and len(attempts) >= K,
    }


def success_by_attempt(task_records: list[dict], K: int) -> list[float]:
    """S(k), k=1..K over a set of task records."""
    n = max(len(task_records), 1)
    out = []
    for k in range(1, K + 1):
        s = sum(1 for r in task_records
                if r["attempts_to_success"] is not None
                and r["attempts_to_success"] <= k)
        out.append(s / n)
    return out


def _mean_sem(vals: list[float]) -> dict:
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"mean": None, "sem": None, "n": 0}
    m = sum(vals) / len(vals)
    if len(vals) < 2:
        return {"mean": m, "sem": None, "n": len(vals)}
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return {"mean": m, "sem": math.sqrt(var / len(vals)), "n": len(vals)}


def aggregate(task_records: list[dict], K: int = 25) -> dict:
    """Suite/split-level aggregation. One record = one sample; standard
    and oracle records never mix; suites never pool."""
    if any(r.get("oracle") for r in task_records) and \
            any(not r.get("oracle") for r in task_records):
        raise ValueError("oracle and standard records must not be pooled")
    suites = {r["suite"] for r in task_records}
    if len(suites) > 1:
        raise ValueError(
            f"records from multiple suites {sorted(suites)} must be "
            f"aggregated separately (source-native results are never "
            f"pooled with controlled or OOD results)")
    curve = success_by_attempt(task_records, K)
    out = {
        "suite": next(iter(suites)) if suites else None,
        "oracle": bool(task_records and task_records[0].get("oracle")),
        "n_task_runs": len(task_records),
        "success_at_K": _mean_sem(
            [1.0 if r["success"] else 0.0 for r in task_records]),
        "success_by_attempt": curve,
        "auc": sum(curve) / max(K, 1),
        "s1": curve[0] if curve else None,
        "adaptation_gain": (sum(curve) / max(K, 1) - curve[0])
                           if curve else None,
        "attempts_to_success": _mean_sem(
            [r["attempts_to_success"] for r in task_records
             if r["attempts_to_success"] is not None]),
        "frames_to_success": _mean_sem(
            [r["frames_to_success"] for r in task_records
             if r["frames_to_success"] is not None]),
        "censored_rate": _mean_sem(
            [1.0 if r["censored"] else 0.0 for r in task_records]),
        "repeated_death_rate": _mean_sem(
            [r["repeated_death_rate"] for r in task_records]),
        "post_discovery_improvement": _mean_sem(
            [r["post_discovery_improvement"] for r in task_records]),
    }
    by_split: dict[str, dict] = {}
    for split in sorted({r["split"] for r in task_records}):
        rs = [r for r in task_records if r["split"] == split]
        c = success_by_attempt(rs, K)
        by_split[split] = {
            "n": len(rs), "s1": c[0] if c else None,
            "auc": sum(c) / max(K, 1),
            "adaptation_gain": (sum(c) / max(K, 1) - c[0]) if c else None,
        }
    out["by_split"] = by_split
    return out


def write_jsonl(records: list[dict], path: str) -> str:
    """Oracle records force the .oracle.jsonl suffix."""
    if any(r.get("oracle") for r in records):
        if not path.endswith(".oracle.jsonl"):
            path = path.rsplit(".jsonl", 1)[0] + ".oracle.jsonl"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return path
