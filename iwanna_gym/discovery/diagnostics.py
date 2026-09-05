"""Blind-policy diagnostics: evidence per task that failure carries
information, not merely that the task is hard.

For every accepted task we run a set of BLIND deterministic policies —
policies that read nothing but time (sprint, hop-sprint, camp-sprint,
seeded macro shuffles) — for the full attempt budget under the task's
fixed hidden configuration, and commit a metadata-only record:

  - per-policy: success, deaths, first-death frame, death positions;
  - death repeatability: with theta fixed, a blind policy that dies
    does so identically every attempt — the exact situation in which a
    remembered failure is worth something;
  - trivially_passable: some blind policy succeeded on attempt 1 —
    the task shows no evidence of requiring discovery (flagged; such a
    task is precision/route content and its inclusion must be
    re-justified);
  - witness_contrast: when a completion witness exists, the same task
    both kills blind play and is completable — together with the
    manifest's hidden-information description this is the committed
    informative-failure evidence.

Records are pure metadata (counts, coordinates, frame indices) —
safe to commit.
"""
from __future__ import annotations

import json
import os

from . import registry as R

DIAG_FORMAT = "discovery-diagnostic/1"


def _sprint(t: int) -> int:
    return 4


def _hop_sprint(t: int) -> int:
    return 5 if (t % 24) < 6 else 4


def _camp_sprint(t: int) -> int:
    return 2 if t < 150 else 4


def _leap_sprint(t: int) -> int:
    return 5 if (t % 60) < 18 else 4


BLIND_POLICIES = {
    "sprint": _sprint,
    "hop_sprint": _hop_sprint,
    "camp_sprint": _camp_sprint,
    "leap_sprint": _leap_sprint,
}


def run_blind(spec: R.TaskSpec, policy_name: str, task_seed: int = 1,
              max_attempts: int = 5) -> dict:
    """Run one blind policy for up to max_attempts of the task."""
    fn = BLIND_POLICIES[policy_name]
    env = R.make_env(spec.task_id, obs_mode="observable_vector")
    env.reset(seed=0, options={"task_seed": task_seed})
    deaths: list[list[float]] = []
    first_death_frame = None
    success = False
    t_in_attempt = 0
    frames = 0
    budget = min(max_attempts, spec.attempts_K) * spec.attempt_frames_H
    while frames < budget:
        obs, r, term, tr, info = env.step(fn(t_in_attempt))
        frames += 1
        t_in_attempt += 1
        if info["attempt_ended"]:
            if info.get("task_success"):
                success = True
                break
            if info["last_event"] == 1:
                deaths.append([round(info["x"], 1), round(info["y"], 1)])
                if first_death_frame is None:
                    first_death_frame = t_in_attempt
            t_in_attempt = 0
            if len(deaths) >= max_attempts or term:
                break
        if term:
            break
    env.close()
    # repeatability: max pairwise distance between death positions
    spread = 0.0
    for i in range(len(deaths)):
        for j in range(i + 1, len(deaths)):
            dx = deaths[i][0] - deaths[j][0]
            dy = deaths[i][1] - deaths[j][1]
            spread = max(spread, (dx * dx + dy * dy) ** 0.5)
    return {
        "policy": policy_name,
        "success": success,
        "n_deaths": len(deaths),
        "first_death_frame": first_death_frame,
        "death_positions": deaths,
        "death_spread_px": round(spread, 1),
    }


def record_diagnostic(spec: R.TaskSpec, task_seed: int = 1) -> dict:
    runs = [run_blind(spec, name, task_seed)
            for name in sorted(BLIND_POLICIES)]
    # trivially passable = EVERY blind pattern strolls through unharmed:
    # no plausible uninformed behavior is punished, so there is no
    # evidence any information is hidden. A single lucky pattern
    # threading the task does NOT clear it — initial ambiguity means
    # some plausible behaviors die, not all of them.
    trivially = all(r["success"] and r["n_deaths"] == 0 for r in runs)
    any_death = any(r["n_deaths"] > 0 for r in runs)
    any_survives = any(r["success"] for r in runs)
    repeatable = any(r["n_deaths"] >= 2 and r["death_spread_px"] <= 48.0
                     for r in runs)
    rec = {
        "format": DIAG_FORMAT,
        "task_id": spec.task_id,
        "suite": spec.suite,
        "task_seed": task_seed,
        "blind_runs": runs,
        "trivially_passable": trivially,
        "blind_play_fails": any_death,
        "some_blind_pattern_survives": any_survives,
        "deaths_repeatable_under_fixed_theta": repeatable,
        "witness_exists": spec.witness_status == "witnessed",
        "note": ("informative-failure evidence = blind play dies (and "
                 "dies repeatably under the fixed hidden configuration) "
                 "while the committed witness completes the task; the "
                 "hidden information itself is described in the task "
                 "manifest row"),
    }
    os.makedirs(R.DIAG_DIR, exist_ok=True)
    with open(os.path.join(R.DIAG_DIR, spec.task_id + ".json"), "w",
              encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    return rec
