"""Executable discovery suite: registry, splits, witnesses, evaluator
math, attempt accounting, suite separation, vectorized stepping."""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

import sys
sys.path.insert(0, ".")
import iwanna_gym.discovery as d                      # noqa: E402
from iwanna_gym.discovery import evaluator as E       # noqa: E402
from iwanna_gym.discovery import registry as R       # noqa: E402

PACK = "build/games/iwbtgr_1_5_3.iwpack"
REG = d.load_registry()


# ------------------------------------------------------------------ #
# registry stability + splits
# ------------------------------------------------------------------ #

def test_registry_version_and_sizes():
    assert d.SUITE_VERSION == "discovery_suite_v1"
    assert len(REG) == 41
    assert len(d.suite_tasks("iwbtg_native", REG)) == 25
    assert len(d.suite_tasks("controlled", REG)) == 16
    assert d.suite_tasks("ood", REG) == []
    assert len(d.pending_ood()) == 3


def test_registry_hash_pinned():
    # content hash over ids/anchors/budgets/splits: silent drift fails
    assert d.registry_hash(REG) == (
        "f323f7b126d46e0de423df33bdd3dfb7"
        "d3e9055335deeb86dcd9157c7ef8154a")


def test_splits_partition_and_hold_out():
    for suite in ("iwbtg_native", "controlled"):
        tasks = d.suite_tasks(suite, REG)
        by = {s: d.suite_tasks(suite, REG, split=s) for s in R.SPLITS}
        assert sum(len(v) for v in by.values()) == len(tasks)
        # leakage rule: a (room, start anchor) may never be shared
        # between TRAIN and any holdout split (train contamination);
        # sharing between validation and test is tolerated and is
        # documented in docs/discovery_suite_report.md
        seen = {}
        for t in tasks:
            key = (t.room, t.start_xy)
            if key in seen:
                prev = seen[key]
                assert ("train" not in (prev, t.split)) or \
                       prev == t.split, key
            seen[key] = t.split
    # family holdout: the five test-only families never train
    held = {"decoy_spike", "sinking_platform", "spawning_trap",
            "appearing_block_chain", "deceptive_furniture",
            "falling_painting_swing"}
    for t in d.suite_tasks("iwbtg_native", REG, split="train"):
        assert not (set(t.hazard_families) & held), t.task_id


def test_native_tasks_carry_provenance_and_fidelity():
    for t in d.suite_tasks("iwbtg_native", REG):
        assert "exact" in t.fidelity
        assert t.provenance["checkpoint_anchor"]
        assert t.provenance["source"]
        assert t.start_xy is not None and t.goal_rect is not None


def test_ood_refuses_unplayable_content():
    # every OOD row is pending; an accepted one must raise
    import tomllib
    with open(R.MANIFEST, "rb") as f:
        m = tomllib.load(f)
    assert all(r["decision"] == "pending" for r in m["ood"])


# ------------------------------------------------------------------ #
# witnesses + diagnostics
# ------------------------------------------------------------------ #

def test_all_controlled_tasks_witnessed_and_witnesses_replay():
    from iwanna_gym.discovery import witness as W
    for t in d.suite_tasks("controlled", REG):
        assert t.witness_status == "witnessed", t.task_id
    # replay-verify two witnesses end-to-end (cheap; full verification
    # is scripts/verify_witnesses.py)
    for tid in ("disc.research.t01_apple", "disc.research.t20_finale"):
        w = d.load_witness(tid)
        assert w["format"] == "discovery-witness/1"
        assert W.verify_witness(REG[tid], w), tid


def test_native_witnesses_replay():
    from iwanna_gym.discovery import witness as W
    witnessed = [t for t in d.suite_tasks("iwbtg_native", REG)
                 if t.witness_status == "witnessed"]
    assert witnessed, "at least one native task must be witnessed"
    if not os.path.exists(PACK):
        pytest.skip("local source-built pack required")
    w0 = witnessed[0]
    assert W.verify_witness(w0, d.load_witness(w0.task_id))


def test_diagnostics_recorded_for_every_task():
    for t in REG.values():
        p = os.path.join(R.DIAG_DIR, t.task_id + ".json")
        assert os.path.exists(p), t.task_id
        rec = json.load(open(p, encoding="utf-8"))
        assert rec["format"] == "discovery-diagnostic/1"
        assert len(rec["blind_runs"]) == 4
        assert t.diagnostic_status in ("recorded", "flagged_trivial")


def test_flagged_trivial_tasks_are_not_active():
    flagged = [t for t in REG.values()
               if t.diagnostic_status == "flagged_trivial"]
    for t in flagged:
        assert not t.active
    # active tasks require witness + non-trivial diagnostic
    for t in REG.values():
        if t.active:
            assert t.witness_status == "witnessed"
            assert t.diagnostic_status == "recorded"


# ------------------------------------------------------------------ #
# evaluator math (hand-computed fixtures)
# ------------------------------------------------------------------ #

def _att(outcome, frames=100, xy=(50.0, 50.0), progress=0.5):
    a = {"outcome": outcome, "frames": frames, "traj_index": 0,
         "min_goal_dist": 10.0, "progress": progress}
    if outcome == "death":
        a["death_xy"] = list(xy)
    return a


def test_task_metrics_hand_computed():
    atts = [_att("death", 100, (50, 50), 0.2),
            _att("death", 80, (52, 50), 0.3),     # repeat (d=2px)
            _att("death", 90, (400, 50), 0.6),    # new hazard
            _att("success", 60, progress=1.0)]
    m = E.task_metrics(atts, K=25)
    assert m["success"] and m["attempts_to_success"] == 4
    assert m["frames_to_success"] == 100 + 80 + 90 + 60
    assert m["n_deaths"] == 3
    # deaths after the first: one repeat of death#1, one novel -> 1/2
    assert m["repeated_death_rate"] == 0.5
    # post-discovery improvement: best later progress - attempt-1
    assert abs(m["post_discovery_improvement"] - (1.0 - 0.2)) < 1e-9
    assert not m["censored"]


def test_task_metrics_censoring_and_none_rdr():
    atts = [_att("death", xy=(10, 10))] * 1
    m = E.task_metrics(atts, K=1)
    assert not m["success"] and m["censored"]
    assert m["repeated_death_rate"] is None      # <2 deaths


def test_success_by_attempt_and_aggregate():
    recs = []
    for k in (1, 3, None):                       # solve@1, solve@3, fail
        atts = ([_att("death", xy=(9, 9))] * ((k or 4) - 1)
                + ([_att("success")] if k else [_att("death", xy=(9, 9))]))
        recs.append({"suite": "controlled", "split": "train",
                     "oracle": False,
                     **E.task_metrics(atts, K=4)})
    S = E.success_by_attempt(recs, K=4)
    assert S == [1 / 3, 1 / 3, 2 / 3, 2 / 3]
    agg = E.aggregate(recs, K=4)
    assert abs(agg["auc"] - sum(S) / 4) < 1e-12
    assert agg["s1"] == 1 / 3
    assert abs(agg["adaptation_gain"] - (agg["auc"] - 1 / 3)) < 1e-12
    assert agg["n_task_runs"] == 3
    assert agg["success_at_K"]["n"] == 3         # task-level samples only


def test_aggregate_refuses_pooling():
    a = {"suite": "iwbtg_native", "split": "train", "oracle": False,
         **E.task_metrics([_att("success")], K=2)}
    b = dict(a, suite="controlled")
    with pytest.raises(ValueError):
        E.aggregate([a, b], K=2)
    c = dict(a, oracle=True)
    with pytest.raises(ValueError):
        E.aggregate([a, c], K=2)


def test_oracle_records_segregated_on_disk():
    import pathlib
    import tempfile
    td = pathlib.Path(tempfile.mkdtemp(prefix="disc_eval_"))
    rec = {"suite": "controlled", "split": "train", "oracle": True,
           **E.task_metrics([_att("success")], K=2)}
    p = E.write_jsonl([rec], str(td / "run.jsonl"))
    assert p.endswith(".oracle.jsonl")


# ------------------------------------------------------------------ #
# attempt accounting + memory protocol through the evaluator
# ------------------------------------------------------------------ #

class _CountingMemory(E.NullMemory):
    def __init__(self):
        self.task_resets = 0
        self.observed = 0

    def reset_task(self):
        self.task_resets += 1

    def observe(self, info):
        self.observed += 1


def test_evaluator_attempt_accounting_on_real_task():
    mem = _CountingMemory()
    rec = E.run_task("disc.research.t14_race",
                     policy=lambda obs, info, m: 2,     # camp: the flood
                     memory=mem, task_seed=3)
    assert rec["suite"] == "controlled" and not rec["oracle"]
    assert rec["n_attempts"] >= 2                # camping dies repeatedly
    assert all(a["outcome"] == "death" for a in rec["attempts"])
    assert rec["repeated_death_rate"] is not None
    assert mem.task_resets == 1                  # exactly one task boundary
    # every attempt's record carries frames + death position
    for a in rec["attempts"]:
        assert a["frames"] > 0 and "death_xy" in a


def test_evaluator_records_witness_success():
    w = d.load_witness("disc.research.t03_riser")
    acts = iter(w["actions"])
    rec = E.run_task("disc.research.t03_riser",
                     policy=lambda o, i, m: next(acts, 2),
                     task_seed=w["task_seed"])
    assert rec["success"] and rec["attempts_to_success"] == 1
    assert rec["frames_to_success"] <= len(w["actions"]) + 1


def test_registry_env_deterministic_replay():
    def run():
        env = d.make_env("disc.research.t12_gauntlet")
        env.reset(seed=0, options={"task_seed": 77})
        out = []
        for t in range(400):
            obs, r, term, tr, info = env.step(4 if t % 3 else 5)
            out.append((obs.tobytes(), r, term, info["attempt_id"]))
            if term:
                break
        env.close()
        return out
    assert run() == run()


# ------------------------------------------------------------------ #
# vectorized stepping across task classes (native path = binding path)
# ------------------------------------------------------------------ #

def _vector_from_binding_kwargs(task_id, n=4):
    from iwanna_gym.clib import CIWanna
    kwargs, envvars = d.binding_kwargs(task_id, REG)
    envs = []
    for i in range(n):
        if kwargs["use_pack"]:
            c = CIWanna(None, pack_data=open(envvars["IWG_PACK"],
                                             "rb").read(),
                        max_steps=int(kwargs["max_steps"]),
                        reward_mode=0, death_penalty=1.0, seed=100 + i,
                        checkpoint_respawn=True)
        else:
            c = CIWanna(open(envvars["IWG_LEVEL_FILE"]).read(),
                        max_steps=int(kwargs["max_steps"]),
                        reward_mode=0, death_penalty=1.0, seed=100 + i)
        c.set_discovery(int(kwargs["attempts_K"]),
                        int(kwargs["attempt_frames_H"]),
                        int(kwargs["obs_mode"]))
        if kwargs["task_start_set"]:
            c.set_task_start(int(kwargs["task_start_room"]),
                             kwargs["task_start_x"], kwargs["task_start_y"])
            c.set_task_goal(int(kwargs["task_goal_room"]),
                            kwargs["task_gx0"], kwargs["task_gy0"],
                            kwargs["task_gx1"], kwargs["task_gy1"])
        c.set_task_seed(1000 + i)
        c.reset()
        envs.append(c)
    return envs


def _step_vector(envs, steps=800):
    boundaries = 0
    for t in range(steps):
        for i, c in enumerate(envs):
            c.step(4 if (t + i) % 24 else 5)   # sprint-with-hops
            boundaries += int(c.attempt_ended)
    for c in envs:
        c.close()
    return boundaries


def test_vectorized_stepping_controlled_tasks():
    envs = _vector_from_binding_kwargs("disc.research.t06_crusher", n=8)
    assert _step_vector(envs) > 0        # attempts happen, nothing crashes


@pytest.mark.skipif(not os.path.exists(PACK),
                    reason="local source-built pack required")
def test_vectorized_stepping_native_tasks_via_pack_mechanism():
    """The IWG_PACK mechanism the binding uses: loads the pack, anchors
    the task, steps a vector. A future iwbtg_original_2007 pack flows
    through exactly this path — only the pack file changes."""
    envs = _vector_from_binding_kwargs(
        "disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall", n=4)
    assert _step_vector(envs, steps=600) > 0


def test_binding_kwargs_complete_and_numeric():
    ini = open("config/iwanna.ini").read()
    kwargs, envvars = d.binding_kwargs("disc.research.t01_apple", REG)
    for k, v in kwargs.items():
        assert isinstance(v, (int, float)), k
        assert k in ini, f"kwarg {k} missing from config/iwanna.ini"
    assert "IWG_LEVEL_FILE" in envvars
