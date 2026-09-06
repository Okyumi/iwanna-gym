"""Pre-registered analysis of the discovery pilot.

Reads build/discovery_pilot/<pilot>/<policy>_s<seed>/eval.jsonl and
computes exactly the pre-registered quantities
(docs/discovery_pilot_prereg.md): per-policy metric tables, the H1
paired gru-vs-gru_reset gap, the H2 interaction against precision
controls, the H3 deathmem-vs-ff repeated-death comparison, and the H4
train-vs-holdout transfer breakdown. Emits machine-readable
analysis.json, a Markdown table fragment, and SVG plots.

    PYTHONPATH=. python scripts/analyze_pilot.py
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys

sys.path.insert(0, ".")
from iwanna_gym.discovery import evaluator as E          # noqa: E402

OUT = os.path.join("build", "discovery_pilot")
K = 25


def _runs(pilot: str) -> dict[tuple[str, int], list[dict]]:
    out = {}
    for f in sorted(glob.glob(os.path.join(OUT, pilot, "*", "eval.jsonl"))):
        name = os.path.basename(os.path.dirname(f))
        policy, s = name.rsplit("_s", 1)
        out[(policy, int(s))] = [json.loads(x) for x in open(f)]
    return out


def _agg(recs: list[dict]) -> dict:
    return E.aggregate(recs, K=K)


def _mean_sd(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, None
    m = sum(vals) / len(vals)
    if len(vals) < 2:
        return m, None
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
    return m, sd


def policy_table(pilot: str, split_filter=None) -> dict:
    """Per-policy metrics: per-seed aggregate first, then mean/sd over
    seeds (a seed's task runs are not independent samples)."""
    runs = _runs(pilot)
    table: dict[str, dict] = {}
    for (policy, seed), recs in runs.items():
        if split_filter:
            recs = [r for r in recs if r["split"] in split_filter]
        if not recs:
            continue
        a = _agg(recs)
        row = table.setdefault(policy, {"seeds": {}, "n_task_runs": 0})
        rdrm = a["repeated_death_rate"]["mean"]
        row["seeds"][seed] = dict(
            success_at_K=a["success_at_K"]["mean"], s1=a["s1"],
            auc=a["auc"], gain=a["adaptation_gain"],
            attempts_to_success=a["attempts_to_success"]["mean"],
            frames_to_success=a["frames_to_success"]["mean"],
            rdr=rdrm, censored=a["censored_rate"]["mean"])
        row["n_task_runs"] += a["n_task_runs"]
    for policy, row in table.items():
        agg = {}
        for k in ("success_at_K", "s1", "auc", "gain",
                  "attempts_to_success", "frames_to_success", "rdr",
                  "censored"):
            m, sd = _mean_sd([s[k] for s in row["seeds"].values()])
            agg[k] = {"mean": m, "sd": sd,
                      "per_seed": {str(i): s[k]
                                   for i, s in row["seeds"].items()}}
        row["metrics"] = agg
        del row["seeds"]
    return table


def paired_gap(pilot: str, a: str, b: str, metric: str = "auc",
               split_filter=None) -> dict:
    """Per-seed paired difference metric(a) - metric(b)."""
    ta = policy_table(pilot, split_filter)
    diffs = []
    if a not in ta or b not in ta:
        return {"diffs": [], "mean": None, "sd": None}
    pa = ta[a]["metrics"][metric]["per_seed"]
    pb = ta[b]["metrics"][metric]["per_seed"]
    for s in sorted(set(pa) & set(pb)):
        if pa[s] is not None and pb[s] is not None:
            diffs.append(pa[s] - pb[s])
    m, sd = _mean_sd(diffs)
    return {"diffs": diffs, "mean": m, "sd": sd,
            "se": (sd / math.sqrt(len(diffs))
                   if sd is not None and diffs else None)}


def curves(pilot: str, split_filter=None) -> dict[str, list[float]]:
    out = {}
    by_policy: dict[str, list[dict]] = {}
    for (policy, seed), recs in _runs(pilot).items():
        if split_filter:
            recs = [r for r in recs if r["split"] in split_filter]
        by_policy.setdefault(policy, []).extend(recs)
    for policy, recs in by_policy.items():
        if recs:
            out[policy] = E.success_by_attempt(recs, K)
    return out


def main() -> int:
    analysis: dict = {"preregistration": "docs/discovery_pilot_prereg.md"}

    for pilot in ("P1", "P2", "P3"):
        if not glob.glob(os.path.join(OUT, pilot, "*", "eval.jsonl")):
            analysis[pilot] = "not run"
            continue
        analysis[pilot] = {"all": policy_table(pilot)}
        if pilot == "P1":
            analysis[pilot]["train_split"] = policy_table(
                pilot, {"train"})
            analysis[pilot]["holdout_split"] = policy_table(
                pilot, {"validation", "test"})

    # H1: gru - gru_reset on P1 (all active discovery tasks)
    analysis["H1_gap_auc"] = paired_gap("P1", "gru", "gru_reset", "auc")
    analysis["H1_gap_successK"] = paired_gap("P1", "gru", "gru_reset",
                                             "success_at_K")
    # H2: the same gap on precision controls; interaction
    analysis["H2_gap_auc_precision"] = paired_gap(
        "P2", "gru", "gru_reset", "auc")
    g1 = analysis["H1_gap_auc"]["mean"]
    g2 = analysis["H2_gap_auc_precision"]["mean"]
    analysis["H2_interaction"] = (None if g1 is None or g2 is None
                                  else g1 - g2)
    # H3: deathmem vs ff repeated-death rate on P1
    analysis["H3_rdr_deathmem_minus_ff"] = paired_gap(
        "P1", "deathmem", "ff", "rdr")
    # H4: per-policy transfer drop on P1
    h4 = {}
    for policy in ("ff", "gru", "gru_reset", "deathmem"):
        tr = policy_table("P1", {"train"}).get(policy)
        ho = policy_table("P1", {"validation", "test"}).get(policy)
        if tr and ho:
            h4[policy] = {
                "train_auc": tr["metrics"]["auc"]["mean"],
                "holdout_auc": ho["metrics"]["auc"]["mean"],
                "train_s1": tr["metrics"]["s1"]["mean"],
                "holdout_s1": ho["metrics"]["s1"]["mean"],
            }
    analysis["H4_transfer"] = h4

    # parameter-count audit
    from iwanna_gym.discovery.baselines import DeathMemory, init_params
    from iwanna_gym.clib import OBS_SIZE
    dm_dim = DeathMemory(1, OBS_SIZE).dim
    counts = {}
    for kind, obs_dim, label in (("ff", OBS_SIZE, "ff"),
                                 ("gru", OBS_SIZE, "gru/gru_reset"),
                                 ("ff", OBS_SIZE + dm_dim, "deathmem")):
        p = init_params(kind, obs_dim, 6, 128, seed=0)
        counts[label] = int(sum(v.size for v in p.values()))
    analysis["parameter_counts"] = counts

    with open(os.path.join(OUT, "analysis.json"), "w",
              encoding="utf-8") as f:
        json.dump(analysis, f, indent=1)

    # ---- markdown tables + SVG curves ----
    lines = ["<!-- generated by scripts/analyze_pilot.py -->"]
    for pilot, label in (("P1", "P1 discovery (all active tasks)"),
                         ("P2", "P2 precision controls"),
                         ("P3", "P3 native chalice_hall")):
        if analysis.get(pilot) in (None, "not run"):
            lines.append(f"\n### {label}: not run\n")
            continue
        lines.append(f"\n### {label}\n")
        lines.append("| policy | S@K | S(1) | AUC | gain | "
                     "attempts→succ | RDR |")
        lines.append("|---|---|---|---|---|---|---|")
        for policy in ("ff", "gru", "gru_reset", "deathmem"):
            row = analysis[pilot]["all"].get(policy) if isinstance(
                analysis[pilot], dict) else None
            if not row:
                continue
            m = row["metrics"]

            def fmt(k):
                v = m[k]["mean"]
                sd = m[k]["sd"]
                if v is None:
                    return "—"
                return (f"{v:.3f}" + (f"±{sd:.3f}" if sd else ""))
            lines.append(
                f"| {policy} | {fmt('success_at_K')} | {fmt('s1')} | "
                f"{fmt('auc')} | {fmt('gain')} | "
                f"{fmt('attempts_to_success')} | {fmt('rdr')} |")
    with open(os.path.join(OUT, "tables.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "dash", "scripts/make_discovery_dashboard.py")
    dash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dash)
    svgs = ["<meta charset='utf-8'><h1>Pilot plots</h1>"]
    for pilot, filt, title in (
            ("P1", None, "P1 discovery: S(k)"),
            ("P1", {"validation", "test"}, "P1 HELD-OUT: S(k)"),
            ("P2", None, "P2 precision controls: S(k)"),
            ("P3", None, "P3 native chalice_hall: S(k)")):
        cs = curves(pilot, filt)
        svgs.append(dash.svg_lines(
            {k: [(i + 1, v) for i, v in enumerate(c)]
             for k, c in cs.items()},
            title, "attempt k", "fraction solved", y01=True))
    with open(os.path.join(OUT, "plots.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(svgs))

    print(json.dumps({k: analysis[k] for k in
                      ("H1_gap_auc", "H2_gap_auc_precision",
                       "H2_interaction", "H3_rdr_deathmem_minus_ff",
                       "H4_transfer", "parameter_counts")}, indent=1))
    print(f"\nwrote {OUT}/analysis.json, tables.md, plots.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
