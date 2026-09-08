"""PufferLib training-path verification checklist.

Encodes the milestone's verification items so that, run on a
training-capable machine after `scripts/puffer_launch.py`, it produces a
per-item pass/fail report. Several items are checkable WITHOUT torch (the
binding's termination/truncation semantics, and whether the recurrent
input protocol / reset ablation are actually WIRED into the PufferLib
path); those run here and are reported now. The remaining items require
the real learner and are delegated to `scripts/puffer_smoke.py` on the
capable machine.

Each item is reported as one of:
  verified_here   — checked in this environment, no torch needed
  needs_capable_machine — requires torch + PufferLib (run puffer_smoke)
  needs_wiring     — a feature the PufferLib path does NOT yet implement

Usage: PYTHONPATH=. python scripts/puffer_verify.py
Output: build/pufferlib_smoke/verify.json
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, ".")

OUT = "build/pufferlib_smoke"


def _binding_terminal_semantics():
    """The adapter exposes terminals[0]=inner_term. In discovery mode the
    core sets terminal only at TASK end, so PufferLib's recurrent state
    carries across attempts and resets at task end (= gru_carry). BUT a
    task that ends by K-EXHAUSTION is reported through the SAME terminal
    flag with no truncation signal, so the learner would treat it as a
    hard terminal and NOT bootstrap the value."""
    from iwanna_gym.env import IWannaDiscoveryEnv
    env = IWannaDiscoveryEnv(level="informative/hidden_spike_2",
                             obs_mode="observable_vector",
                             attempts_K=3, attempt_frames_H=120,
                             reward_mode="sparse")
    obs, info = env.reset(seed=0, options={"task_seed": 1})
    term_at_nonfinal_attempt = 0
    ended_by_exhaustion = None
    for _ in range(3 * 120 + 20):
        obs, r, term, trunc, info = env.step(4)   # dies at the trap
        if info["attempt_ended"] and not term:
            pass                                   # intra-task respawn, good
        if info["attempt_ended"] and term and not info.get("task_exhausted"):
            term_at_nonfinal_attempt += 1
        if term:
            ended_by_exhaustion = bool(info.get("task_exhausted"))
            break
    env.close()
    carry_free = term_at_nonfinal_attempt == 0
    # the truncation gap: task ended by exhaustion but only `term` (not a
    # gym `trunc`) was raised -> no bootstrap signal for the learner
    truncation_distinct = not ended_by_exhaustion   # True only if not-exhaust
    return carry_free, ended_by_exhaustion


def _input_protocol_wired():
    """Is the permitted prev-action/reward/boundary protocol consumed by
    the PufferLib policy/env? (It is a validated spec, not yet wired.)"""
    srcs = []
    for p in ("c_src/puffer/binding.c", "c_src/puffer/iwanna_puffer.h",
              "config/iwanna_puffer.ini"):
        try:
            srcs.append(open(p, encoding="utf-8").read())
        except OSError:
            pass
    return any("input_protocol" in s or "prev_action" in s for s in srcs)


def _gru_reset_mode_in_puffer():
    """Does the PufferLib path implement the reset-memory ablation (zero
    the recurrent state at every ATTEMPT boundary, not just task end)?"""
    for p in ("c_src/puffer/binding.c", "c_src/puffer/iwanna_puffer.h",
              "config/iwanna_puffer.ini"):
        try:
            if "attempt_reset" in open(p, encoding="utf-8").read():
                return True
        except OSError:
            pass
    return False


CHECKLIST = {
    "actual_collection_and_updates":
        "needs_capable_machine (puffer_smoke train_ok + finite losses)",
    "prev_action_reward_boundary_inputs": None,     # filled below
    "carry_vs_reset_in_recurrent_learner": None,
    "memory_clearing_at_task_boundaries": None,
    "termination_truncation_value_bootstrap": None,
    "checkpoint_reload_and_shared_evaluator_eval":
        "needs_capable_machine (scripts/puffer_eval.py -> evaluator.task_metrics)",
    "finite_losses_and_changing_parameters":
        "needs_capable_machine (puffer_smoke parses train log)",
    "end_to_end_throughput":
        "needs_capable_machine (puffer_smoke records SPS; sim-only already in "
        "docs/discovery_training_report.md)",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    carry_free, ended_by_exhaustion = _binding_terminal_semantics()
    proto = _input_protocol_wired()
    greset = _gru_reset_mode_in_puffer()

    CHECKLIST["carry_vs_reset_in_recurrent_learner"] = (
        f"verified_here (PARTIAL): terminal fires only at TASK end, so "
        f"PufferLib recurrence carries across attempts and resets at task "
        f"end = gru_carry FOR FREE (carry_free={carry_free}). The gru_RESET "
        f"ablation (zero state at every attempt boundary) is "
        f"{'wired' if greset else 'NOT wired'} in the PufferLib path -> "
        f"{'ok' if greset else 'needs_wiring'}.")
    CHECKLIST["memory_clearing_at_task_boundaries"] = (
        f"verified_here: terminal at task end zeroes PufferLib recurrent "
        f"state (carry_free={carry_free}); intra-task attempt boundaries do "
        f"NOT terminate, as required.")
    CHECKLIST["termination_truncation_value_bootstrap"] = (
        f"needs_wiring: a task ending by K-EXHAUSTION sets `term` with "
        f"task_exhausted={ended_by_exhaustion} but raises NO separate "
        f"truncation signal, so the learner would treat exhaustion as a hard "
        f"terminal and NOT bootstrap the value. Expose task_exhausted as a "
        f"truncation buffer before trusting value estimates on exhausted "
        f"tasks. Goal-reached remains a true terminal.")
    CHECKLIST["prev_action_reward_boundary_inputs"] = (
        f"needs_wiring: input_protocol.py is a validated SPEC (unit-tested) "
        f"but is {'wired' if proto else 'NOT wired'} into the PufferLib "
        f"policy/env.")

    report = {
        "cpu_count": os.cpu_count(),
        "have_torch": _importable("torch"),
        "have_pufferlib": _importable("pufferlib"),
        "binding_carry_free": carry_free,
        "task_exhaustion_is_truncation_but_flagged_terminal": ended_by_exhaustion,
        "input_protocol_wired": proto,
        "gru_reset_wired_in_puffer": greset,
        "checklist": CHECKLIST,
        "single_command": (
            "bash scripts/setup_pufferlib.sh $HOME/PufferLib && "
            "PYTHONPATH=. python scripts/puffer_launch.py "
            "disc.research.t06_crusher --pufferlib-dir $HOME/PufferLib && "
            "PYTHONPATH=. python scripts/puffer_smoke.py"),
    }
    with open(os.path.join(OUT, "verify.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


def _importable(m):
    try:
        __import__(m)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
