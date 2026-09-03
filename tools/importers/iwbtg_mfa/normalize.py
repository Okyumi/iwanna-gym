"""Normalize a CTFAK inventory dump into the source-derived inventory.

Input contract: ``ctfak-inventory-dump/1`` — a single JSON document
emitted by the external CTFAK 2.0 InventoryDump plugin (spec:
docs/iwbtg_mfa_feasibility.md, field names mirror CTFAK.Core's public
model: MFAData, MFAFrame, MFAObjectInfo/Instance, MFAEvents/EventGroup,
MFAMovements, MFATransition, MFAValueList).  The dump carries METADATA
ONLY (names, handles, coordinates, numeric parameters, chunk ids) —
never images, sounds, or other expressive assets.

Output: a normalized inventory with
  - counts by record type,
  - per-record provenance back to the MFA identity (frame handle+name,
    object handle, event group index, condition/action ordinal),
  - a coverage ledger that FAILS CLOSED: any unparsed record, any
    gameplay-relevant unknown chunk, or any event atom missing its
    identity raises CoverageError.  Nothing is silently skipped —
    every record either lands in the inventory or in the raised error.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

DUMP_FORMAT = "ctfak-inventory-dump/1"

#: MFA chunk ids that carry no gameplay semantics (banks, editor
#: cosmetics, shader visuals).  Unknown chunks OUTSIDE this set are
#: gameplay-relevant by definition and fail the gate.
COSMETIC_CHUNKS = {
    "AGMI", "ATNF", "ASUM", "APMS",          # image/font/music/sound banks
    "icon", "stamp", "editor_layout",
    "shader", "ObjectShaderSettings", "FrameShaderSettings",
    "LayerShaderSettings", "comments", "Rems",
    "EvCs", "EvEd", "EvTs", "EvLs",          # event-editor UI state
}

#: record kinds the normalizer understands; anything else in the dump
#: is unsupported and fails closed
GAMEPLAY_SECTIONS = ("app", "frames", "objects", "extensions")


class DumpFormatError(ValueError):
    """The dump is not a well-formed ctfak-inventory-dump/1 document."""


class CoverageError(ValueError):
    """Unsupported or unknown gameplay-relevant records were found."""


def _req(d: dict, key: str, where: str):
    if key not in d:
        raise DumpFormatError(f"{where}: missing required field {key!r}")
    return d[key]


def normalize_dump(dump: dict[str, Any]) -> dict[str, Any]:
    if dump.get("dump_format") != DUMP_FORMAT:
        raise DumpFormatError(
            f"expected dump_format {DUMP_FORMAT!r}, got "
            f"{dump.get('dump_format')!r}")
    for sec in GAMEPLAY_SECTIONS:
        _req(dump, sec, "dump")

    counts: Counter = Counter()
    problems: list[str] = []
    inv: dict[str, Any] = {
        "format": "iwbtg-normalized-inventory/1",
        "source_sha256": dump.get("source_sha256", ""),
        "ctfak_commit": dump.get("ctfak_commit", ""),
        "app": {}, "frames": [], "objects": [], "extensions": [],
        "unknown_chunks": {"cosmetic": [], "gameplay_relevant": []},
        "counts": {}, "problems": [],
    }

    # ---- application-level records
    app = dump["app"]
    inv["app"] = {
        "name": _req(app, "name", "app"),
        "mfa_version": _req(app, "mfa_version", "app"),
        "mfa_subversion": app.get("mfa_subversion"),
        "build_version": _req(app, "build_version", "app"),
        "product": app.get("product"),
        "window": _req(app, "window", "app"),
        "frame_order": list(_req(app, "frame_order", "app")),
        "global_values": [
            {"index": _req(v, "index", "global_values"),
             "value": _req(v, "value", "global_values")}
            for v in app.get("global_values", [])],
        "global_strings": [
            {"index": _req(s, "index", "global_strings"),
             "value": _req(s, "value", "global_strings")}
            for s in app.get("global_strings", [])],
    }
    counts["global_values"] = len(inv["app"]["global_values"])
    counts["global_strings"] = len(inv["app"]["global_strings"])

    # ---- object definitions (with movements, counters, qualifiers)
    handles = {}
    for o in dump["objects"]:
        where = f"objects[{o.get('handle', '?')}]"
        rec = {
            "handle": _req(o, "handle", where),
            "name": _req(o, "name", where),
            "type_id": _req(o, "type_id", where),
            "type_name": o.get("type_name", ""),
            "loader_kind": o.get("loader_kind", ""),
            "qualifiers": list(o.get("qualifiers", [])),
            "group": o.get("group"),
            "parent_handle": o.get("parent_handle"),
            "movements": [],
            "counter": o.get("counter"),
            "provenance": {"mfa_object_handle": o["handle"],
                           "mfa_object_name": o["name"]},
        }
        if o.get("unparsed"):
            problems.append(f"{where} ({o['name']}): loader reported "
                            f"unparsed object data")
        for mi, m in enumerate(o.get("movements", [])):
            mwhere = f"{where}/movements[{mi}]"
            rec["movements"].append({
                "index": mi,
                "name": m.get("name", ""),
                "type_id": _req(m, "type_id", mwhere),
                "type_name": m.get("type_name", ""),
                "extension": m.get("extension"),
                "player": m.get("player"),
                "moving_at_start": m.get("moving_at_start"),
                "direction_at_start": m.get("direction_at_start"),
                "params": m.get("params", {}),
                "provenance": {"mfa_object_handle": o["handle"],
                               "movement_index": mi},
            })
        counts["movements"] += len(rec["movements"])
        counts["qualifier_links"] += len(rec["qualifiers"])
        if rec["counter"] is not None:
            counts["counters"] += 1
        handles[rec["handle"]] = rec["name"]
        inv["objects"].append(rec)
    counts["objects"] = len(inv["objects"])

    # ---- extensions
    for e in dump["extensions"]:
        where = f"extensions[{e.get('handle', '?')}]"
        inv["extensions"].append({
            "handle": _req(e, "handle", where),
            "name": _req(e, "name", where),
            "subtype": e.get("subtype"),
        })
    counts["extensions"] = len(inv["extensions"])

    # ---- frames: instances, transitions, event sheets
    frame_handles = set()
    for f in dump["frames"]:
        fw = f"frames[{f.get('handle', '?')}]"
        fh = _req(f, "handle", fw)
        fname = _req(f, "name", fw)
        frame_handles.add(fh)
        frec: dict[str, Any] = {
            "handle": fh, "name": fname,
            "size": _req(f, "size", fw),
            "layers": f.get("layers", 1),
            "transitions": f.get("transitions", {}),
            "instances": [], "events": {"groups": []},
            "provenance": {"mfa_frame_handle": fh,
                           "mfa_frame_name": fname},
        }
        if frec["transitions"]:
            counts["transitions"] += len(frec["transitions"])
        for inst in f.get("instances", []):
            iw = f"{fw}/instances[{inst.get('instance_id', '?')}]"
            frec["instances"].append({
                "instance_id": _req(inst, "instance_id", iw),
                "object_handle": _req(inst, "object_handle", iw),
                "object_name": handles.get(inst["object_handle"]),
                "x": _req(inst, "x", iw), "y": _req(inst, "y", iw),
                "layer": inst.get("layer", 0),
                "flags": inst.get("flags", 0),
                "parent_type": inst.get("parent_type"),
                "parent_handle": inst.get("parent_handle"),
                "provenance": {"mfa_frame_handle": fh,
                               "mfa_instance_id": inst["instance_id"],
                               "mfa_object_handle": inst["object_handle"]},
            })
            if inst["object_handle"] not in handles:
                problems.append(f"{iw}: instance references unknown "
                                f"object handle {inst['object_handle']}")
        counts["instances"] += len(frec["instances"])

        ev = f.get("events", {})
        for gi, g in enumerate(ev.get("groups", [])):
            gw = f"{fw}/events/groups[{gi}]"
            grec = {
                "index": gi,
                "identifier": g.get("identifier"),
                "flags": g.get("flags", 0),
                "restricted": g.get("restricted", 0),
                "container": g.get("container"),   # nested-group parent
                "is_group_marker": bool(g.get("is_group_marker", False)),
                "conditions": [], "actions": [],
                "provenance": {"mfa_frame_handle": fh,
                               "event_group_index": gi,
                               "event_group_identifier": g.get(
                                   "identifier")},
            }
            for kind in ("conditions", "actions"):
                for ai, a in enumerate(g.get(kind, [])):
                    aw = f"{gw}/{kind}[{ai}]"
                    if "num" not in a or "object_type" not in a:
                        problems.append(
                            f"{aw}: event atom missing num/object_type "
                            f"identity")
                        continue
                    grec[kind].append({
                        "ordinal": ai,
                        "num": a["num"],
                        "object_type": a["object_type"],
                        "object_handle": a.get("object_handle"),
                        "qualifier": a.get("qualifier"),
                        "expressions": a.get("expressions", []),
                        "provenance": {"mfa_frame_handle": fh,
                                       "event_group_index": gi,
                                       "atom_kind": kind,
                                       "atom_ordinal": ai},
                    })
                    counts["expressions"] += len(a.get("expressions", []))
            counts["conditions"] += len(grec["conditions"])
            counts["actions"] += len(grec["actions"])
            if grec["is_group_marker"]:
                counts["nested_groups"] += 1
            frec["events"]["groups"].append(grec)
        counts["event_groups"] += len(frec["events"]["groups"])
        inv["frames"].append(frec)
    counts["frames"] = len(inv["frames"])

    # frame_order must reference known frames
    for fh in inv["app"]["frame_order"]:
        if fh not in frame_handles:
            problems.append(f"app/frame_order references unknown frame "
                            f"handle {fh}")

    # ---- unknown chunks: cosmetic pass, gameplay-relevant fail
    for u in dump.get("unknown_chunks", []):
        rec = {"where": u.get("where", "?"),
               "chunk_id": str(u.get("chunk_id", "?")),
               "size": u.get("size", 0)}
        if rec["chunk_id"] in COSMETIC_CHUNKS:
            inv["unknown_chunks"]["cosmetic"].append(rec)
        else:
            inv["unknown_chunks"]["gameplay_relevant"].append(rec)
    counts["unknown_chunks_cosmetic"] = \
        len(inv["unknown_chunks"]["cosmetic"])
    counts["unknown_chunks_gameplay"] = \
        len(inv["unknown_chunks"]["gameplay_relevant"])

    # ---- any explicitly unsupported records from the dumper
    for u in dump.get("unsupported", []):
        problems.append(f"{u.get('where', '?')}: dumper marked "
                        f"unsupported: {u.get('note', '')}")

    inv["counts"] = dict(counts)
    inv["problems"] = problems

    # ---- the fail-closed gate
    gate: list[str] = []
    gate.extend(problems)
    for rec in inv["unknown_chunks"]["gameplay_relevant"]:
        gate.append(f"gameplay-relevant unknown chunk "
                    f"{rec['chunk_id']!r} at {rec['where']} "
                    f"({rec['size']} bytes)")
    if gate:
        raise CoverageError(
            "the extraction is NOT complete enough to proceed; "
            f"{len(gate)} blocking record(s):\n  - " +
            "\n  - ".join(gate[:40]))
    return inv


def report_text(inv: dict[str, Any]) -> str:
    lines = [f"normalized inventory for {inv['app']['name']!r} "
             f"(mfa {inv['app']['mfa_version']}."
             f"{inv['app'].get('mfa_subversion')})",
             f"source sha256: {inv.get('source_sha256', '')[:16]}…",
             f"ctfak commit:  {inv.get('ctfak_commit', '')[:12]}",
             "counts by record type:"]
    for k, v in sorted(inv["counts"].items()):
        lines.append(f"  {k:28s} {v}")
    lines.append(f"frames in order: "
                 f"{len(inv['app']['frame_order'])} "
                 f"(handles {inv['app']['frame_order'][:12]}…)"
                 if len(inv['app']['frame_order']) > 12 else
                 f"frames in order: {inv['app']['frame_order']}")
    lines.append("coverage: PASS (no unsupported or gameplay-relevant "
                 "unknown records)")
    return "\n".join(lines)


def load_dump(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
