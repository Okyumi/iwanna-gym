"""Consistency checks for the discovery-benchmark design milestone.

Validates manifests/discovery_task_candidates.toml against the contract
(docs/discovery_benchmark_contract.md) and against the committed source
inventory — so a stale manifest, a fabricated room, a split leak, or an
unauthorized original-2007 row fails CI.
"""
from __future__ import annotations

import os
import re
import tomllib

MANIFEST = "manifests/discovery_task_candidates.toml"
CONTRACT = "docs/discovery_benchmark_contract.md"

with open(MANIFEST, "rb") as f:
    M = tomllib.load(f)

NATIVE = M.get("native", [])
CONTROLLED = M.get("controlled", [])
OOD = M.get("ood", [])
ALL = NATIVE + CONTROLLED + OOD


def _accepted(rows):
    return [r for r in rows if r.get("decision") == "accept"]


def test_ids_unique_and_stable_shape():
    ids = [r["id"] for r in ALL]
    assert len(ids) == len(set(ids)), "duplicate task ids"
    for i in ids:
        assert re.fullmatch(r"disc\.[A-Za-z0-9_]+\.[A-Za-z0-9_,\s]+(\.[A-Za-z0-9_]+)?", i), i


def test_every_row_has_decision_and_evidence_or_reason():
    for r in ALL:
        assert r.get("decision") in ("accept", "exclude", "pending"), r["id"]
        if r["decision"] == "accept":
            assert r.get("hidden_info") and r.get("failure_reveals"), r["id"]
            assert r.get("split") in ("train", "validation", "test"), r["id"]
            assert r.get("fidelity", {}).get("label"), r["id"]
            assert r.get("budget", {}).get("K", 0) > 0, r["id"]
        else:
            assert r.get("reason"), r["id"]


def test_no_original_2007_content_is_accepted():
    for r in ALL:
        if r.get("game") == "iwbtg_original_2007":
            assert r["decision"] != "accept", \
                "original-2007 tasks require a genuinely available import"


def test_native_rooms_and_anchors_exist_in_source_inventory():
    import json
    rep = "build/source_reports/iwbtgr_1_5_3.json"
    if not os.path.exists(rep):
        import pytest
        pytest.skip("source inventory not built in this environment")
    src = json.load(open(rep, encoding="utf-8"))
    rooms = {r["name"]: r for r in src["rooms"]}
    for r in _accepted(NATIVE):
        assert r["room"] in rooms, r["id"]
        cp = r["checkpoint"]
        insts = rooms[r["room"]]["instances"]
        hit = [i for i in insts
               if i["object"].startswith(("save", "playerStart"))
               and i["x"] == cp["x"] and i["y"] == cp["y"]]
        assert hit, f"{r['id']}: no save/playerStart at ({cp['x']},{cp['y']})"
        assert hit[0]["object"] == cp["anchor"], \
            f"{r['id']}: anchor {cp['anchor']} != source {hit[0]['object']}"


def test_controlled_rooms_exist_as_level_files():
    for r in CONTROLLED:
        if r["decision"] == "accept":
            path = os.path.join("iwanna_gym", "levels", r["room"] + ".txt")
            assert os.path.exists(path), path


def test_family_holdouts_do_not_leak_into_training():
    held = set()
    for r in _accepted(NATIVE):
        if r.get("split") == "test" and r.get("held_out_family"):
            held.add(r["held_out_family"].split(" ")[0].rstrip("(,"))
    assert held, "test rows must declare held-out families"
    for r in _accepted(NATIVE) + _accepted(CONTROLLED):
        if r.get("split") == "train":
            fams = set(r.get("hazard_families", []))
            leak = fams & held
            assert not leak, f"{r['id']}: held-out family {leak} in training"


def test_split_counts_match_summary_comment():
    acc = _accepted(NATIVE)
    by = {s: sum(1 for r in acc if r["split"] == s)
          for s in ("train", "validation", "test")}
    assert len(acc) == 25 and by == {"train": 14, "validation": 6, "test": 5}
    accc = _accepted(CONTROLLED)
    byc = {s: sum(1 for r in accc if r["split"] == s)
           for s in ("train", "validation", "test")}
    assert len(accc) == 16 and byc == {"train": 11, "validation": 3, "test": 2}
    assert all(r["decision"] == "pending" for r in OOD) and len(OOD) == 3


def test_ood_is_never_headline():
    for r in OOD:
        assert r.get("game") != "iwbtgr_1_5_3_v1"
        assert r.get("split") in ("test", "none", None)


def test_contract_document_covers_required_sections():
    text = " ".join(open(CONTRACT, encoding="utf-8").read().split())
    for needle in (
        "unit of evaluation", "attempt reset", "task reset",
        "Latent hazard information", "hidden configuration",
        "Success@K", "Repeated-death rate",
        "Anti-leakage", "trigger rectangles", "task IDs",
        "screen and hazard family",
        "Remastered", "NOT the original 2007",
        "PufferLib", "wall-clock", "GIF",
    ):
        assert needle.lower() in text.lower(), f"contract missing: {needle}"
    # the Remastered/original distinction must be explicit
    assert "iwbtg_original_2007" in text and "iwbtgr_1_5_3" in text


def test_leak_findings_are_recorded():
    text = open(CONTRACT, encoding="utf-8").read()
    assert "L1" in text and "L2" in text and "TRAP_DORMANT" in text
