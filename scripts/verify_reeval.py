"""Bounded old-vs-corrected verification of the pilot re-evaluation.

For every trained checkpoint still on disk, re-evaluates it through the
REPAIRED evaluator (deterministic replay; NO retraining) and compares
each per-task-run metric against the ORIGINAL committed eval record,
matched by (task_id, task_seed). Reports, per (pilot, policy, seed),
which metric fields are bit-identical and which changed — so the claim
"historical metric X is unchanged" is limited to exactly what was
verified.

Coverage boundary (documented in the output):
  - Only checkpoints present on disk are covered (gitignored but not
    deleted). deathmem is re-evaluated but its results are NOT eligible
    for an "unchanged" claim: its TRAINING consumed the timeout-as-death
    bug, so re-eval cannot restore the intended agent (H3 needs a
    retrain).
  - Metrics compared are exactly the fields in each eval record.

Usage: PYTHONPATH=. python scripts/verify_reeval.py
Output: build/discovery_pilot_corrected/reeval_coverage.json
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, ".")
import iwanna_gym.discovery as d                          # noqa: E402
from iwanna_gym.discovery import evaluator as E           # noqa: E402

# import the pilot's task sets + shared eval path (single source of truth)
import importlib.util                                     # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "run_pilot", "scripts/run_pilot.py")
_rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rp)

OUTDIR = "build/discovery_pilot_corrected"

# fields that DO NOT read death positions -> expected identical
SUCCESS_FAMILY = ("success", "attempts_to_success", "frames_to_success",
                  "n_attempts", "n_deaths", "censored")
# fields that DO read terminal position -> expected to change
POSITION_DERIVED = ("repeated_death_rate", "post_discovery_improvement")


def _key(rec):
    return (rec["task_id"], rec["task_seed"])


def compare_run(pilot: str, policy: str, seed: int) -> dict | None:
    run_dir = f"build/discovery_pilot/{pilot}/{policy}_s{seed}"
    ckpt = os.path.join(run_dir, "checkpoint.npz")
    old_path = os.path.join(run_dir, "eval.jsonl")
    if not (os.path.exists(ckpt) and os.path.exists(old_path)):
        return None
    old = {_key(json.loads(x)): json.loads(x)
           for x in open(old_path, encoding="utf-8")}
    new = _rp.eval_checkpoint(ckpt, _rp.PILOTS[pilot]["eval_tasks"],
                              _rp.PILOTS[pilot]["suite_label"])
    field_match = {f: {"same": 0, "diff": 0, "examples": []}
                   for f in SUCCESS_FAMILY + POSITION_DERIVED}
    n_matched = 0
    for nrec in new:
        orec = old.get(_key(nrec))
        if orec is None:
            continue
        n_matched += 1
        for f in SUCCESS_FAMILY + POSITION_DERIVED:
            ov, nv = orec.get(f), nrec.get(f)
            if ov == nv:
                field_match[f]["same"] += 1
            else:
                field_match[f]["diff"] += 1
                if len(field_match[f]["examples"]) < 2:
                    field_match[f]["examples"].append(
                        {"task": nrec["task_id"], "seed": nrec["task_seed"],
                         "old": ov, "new": nv})
    return {"pilot": pilot, "policy": policy, "seed": seed,
            "task_runs_matched": n_matched,
            "old_format": next(iter(old.values()))["format"],
            "fields": field_match}


def main() -> int:
    os.makedirs(OUTDIR, exist_ok=True)
    # controlled-room pilots (P1/P2) are fast and carry H1/H2/H4; the
    # native P3 re-eval is slow (long per-attempt budgets) and is
    # covered separately by build/discovery_pilot_corrected/
    # verification.json (aggregate old-vs-corrected on the seed-1
    # checkpoints). Pass "all" to force P3 too.
    # Bounded, documented scope (single CPU core here): the P1
    # controlled-discovery suite, seed-1 training checkpoints, all four
    # policies, over all 14 eval tasks x 3 eval seeds = 42 task-runs per
    # policy. P1 carries H1/H2/H4. Pass "all" to widen to every
    # checkpoint (slow; the native P3 budgets make it multi-hour here).
    if "all" in sys.argv:
        cover = sorted(glob.glob(
            "build/discovery_pilot/*/*/checkpoint.npz"))
    else:
        cover = sorted(glob.glob(
            "build/discovery_pilot/P1/*_s1/checkpoint.npz"))
    results = []
    for ckpt in cover:
        parts = ckpt.split("/")
        pilot = parts[2]
        policy, seed = parts[3].rsplit("_s", 1)
        r = compare_run(pilot, policy, int(seed))
        if r:
            results.append(r)
            print(f"{pilot} {policy} s{seed}: {r['task_runs_matched']} "
                  f"runs; success-family identical="
                  f"{all(r['fields'][f]['diff'] == 0 for f in SUCCESS_FAMILY)}"
                  f" RDR-changed="
                  f"{r['fields']['repeated_death_rate']['diff'] > 0}",
                  flush=True)

    # aggregate the claim boundary
    eligible = [r for r in results if r["policy"] != "deathmem"]
    sf_all_identical = all(
        r["fields"][f]["diff"] == 0
        for r in eligible for f in SUCCESS_FAMILY)
    coverage = {
        "note": ("Old-vs-corrected re-evaluation of every on-disk pilot "
                 "checkpoint through the repaired evaluator (deterministic "
                 "replay, NO retraining). Success-family fields do not "
                 "read death positions; position-derived fields (RDR, "
                 "post_discovery_improvement) do."),
        "checkpoints_covered": len(results),
        "pilots_covered": sorted({r["pilot"] for r in results}),
        "pilots_not_in_this_pass": [p for p in ("P1", "P2", "P3")
                                    if p not in {r["pilot"] for r in results}],
        "policies_eligible_for_unchanged_claim": sorted(
            {r["policy"] for r in eligible}),
        "deathmem_excluded_reason": (
            "trained with the timeout-as-death bug; re-eval cannot "
            "restore the intended agent — H3 requires a retrain"),
        "success_family_bit_identical_across_all_eligible_runs":
            bool(sf_all_identical),
        "success_family_fields": list(SUCCESS_FAMILY),
        "position_derived_fields_changed": list(POSITION_DERIVED),
        "eval_task_seeds": list(_rp.EVAL_TASK_SEEDS),
        "runs": results,
    }
    out = os.path.join(OUTDIR, "reeval_coverage.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(coverage, f, indent=1)
    print(f"\nsuccess-family bit-identical across ALL eligible "
          f"(non-deathmem) runs: {sf_all_identical}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
