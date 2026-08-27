"""Validator for the canonical IR (.iwgame.json).

Policy (docs/importer_architecture.md): elements with mapping_status
``unsupported`` or ``unknown`` are validation ERRORS unless
``allow_unsupported=True`` (inspection mode), in which case they are
reported as warnings. Nothing is ever silently discarded — the compiler
enforces the same rule again at compile time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schema import (
    ACTION_PROFILES,
    ENTITY_KINDS,
    EVENT_ACTIONS,
    EVENT_WHEN,
    FORMAT_VERSION,
    MAPPING_STATUSES,
    PHYSICS_PROFILES,
    TILE_CHARS,
    iter_elements,
)

_EDGES = ("left", "right", "up", "down")
_PROVENANCE_KEYS = ("source_game", "source_version", "source_format",
                    "source_checksum_sha256", "importer", "importer_version")


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status_counts: dict[str, int] = field(default_factory=dict)
    unsupported: list[str] = field(default_factory=list)  # where-paths

    @property
    def ok(self) -> bool:
        return not self.errors

    def text(self) -> str:
        lines = []
        lines.append("validation: " + ("OK" if self.ok else "FAILED"))
        lines.append("mapping statuses: " + (
            ", ".join(f"{k}={v}" for k, v in sorted(self.status_counts.items()))
            or "none"))
        for w in self.warnings:
            lines.append(f"  warning: {w}")
        for e in self.errors:
            lines.append(f"  error: {e}")
        return "\n".join(lines)


def validate(doc: dict[str, Any], allow_unsupported: bool = False) -> ValidationReport:
    rep = ValidationReport()
    err = rep.errors.append
    warn = rep.warnings.append

    if doc.get("format") != FORMAT_VERSION:
        err(f"format is {doc.get('format')!r}, expected {FORMAT_VERSION!r}")
        return rep

    md = doc.get("metadata", {})
    if not md.get("game_id"):
        err("metadata.game_id is required")

    prov = doc.get("provenance", {})
    for k in _PROVENANCE_KEYS:
        if k not in prov:
            warn(f"provenance.{k} missing")

    if doc.get("physics_profile") not in PHYSICS_PROFILES:
        err(f"physics_profile {doc.get('physics_profile')!r} is not an "
            f"implemented profile {sorted(PHYSICS_PROFILES)} — a pack must "
            "never claim a profile the runtime does not implement")
    if doc.get("action_profile") not in ACTION_PROFILES:
        err(f"action_profile {doc.get('action_profile')!r} not in "
            f"{sorted(ACTION_PROFILES)}")

    # global flags
    flag_ids = set()
    for fl in doc.get("global_flags", []):
        fid = fl.get("id")
        if not isinstance(fid, int) or not (1 <= fid <= 63):
            err(f"global flag {fl.get('name')!r}: id must be an int in 1..63")
        elif fid in flag_ids:
            err(f"global flag id {fid} defined twice")
        else:
            flag_ids.add(fid)

    # object definitions
    objdefs: dict[str, dict] = {}
    for od in doc.get("object_definitions", []):
        name = od.get("name")
        if not name:
            err("object definition without a name")
            continue
        if name in objdefs:
            err(f"object {name!r} defined twice")
        objdefs[name] = od
        kind = od.get("kind")
        if od.get("mapping_status") in ("exact", "equivalent"):
            if kind not in ENTITY_KINDS and kind not in (
                    "tile_block", "tile_spike_up", "tile_spike_down",
                    "tile_spike_left", "tile_spike_right", "tile_goal",
                    "player_start"):
                err(f"object {name!r}: kind {kind!r} is not a runtime kind "
                    "but is marked as mapped — mark it unsupported/unknown "
                    "instead of guessing")

    # rooms
    rooms = doc.get("rooms", [])
    if not rooms:
        err("no rooms")
    ids = [r.get("id") for r in rooms]
    if ids != list(range(len(rooms))):
        err(f"room ids must be 0..{len(rooms)-1} in order, got {ids}")
    n_rooms = len(rooms)
    start_seen = False
    for room in rooms:
        rn = room.get("name", room.get("id"))
        w, h = room.get("width_tiles"), room.get("height_tiles")
        if not (isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0):
            err(f"room {rn}: bad dimensions {w}x{h}")
            continue
        tiles = room.get("tiles", [])
        if len(tiles) != h or any(len(row) != w for row in tiles):
            err(f"room {rn}: tiles must be {h} rows of {w} chars")
        else:
            for y, row in enumerate(tiles):
                for x, ch in enumerate(row):
                    if ch not in TILE_CHARS:
                        err(f"room {rn}: unknown tile char {ch!r} at {x},{y}")
        if room.get("start"):
            start_seen = start_seen or room["id"] == doc["room_graph"].get("start_room")
        for e in _EDGES:
            tgt = room.get("edges", {}).get(e)
            if tgt is not None and (not isinstance(tgt, int) or not 0 <= tgt < n_rooms):
                err(f"room {rn}: edge {e} -> {tgt!r} is not a valid room id")
        for i, inst in enumerate(room.get("instances", [])):
            oname = inst.get("object")
            if oname not in objdefs:
                err(f"room {rn} instance[{i}]: unknown object {oname!r} "
                    "(no object definition)")
            if not isinstance(inst.get("x"), (int, float)) or \
               not isinstance(inst.get("y"), (int, float)):
                err(f"room {rn} instance[{i}] ({oname}): missing x/y")
        for i, ev in enumerate(room.get("events", [])):
            if ev.get("mapping_status") in ("exact", "equivalent"):
                if ev.get("when") not in EVENT_WHEN:
                    err(f"room {rn} event[{i}]: unknown condition "
                        f"{ev.get('when')!r} marked as mapped")
                for j, a in enumerate(ev.get("actions", [])):
                    if a.get("do") not in EVENT_ACTIONS:
                        err(f"room {rn} event[{i}] action[{j}]: unknown action "
                            f"{a.get('do')!r} marked as mapped")
                    for fk in ("id", "flag"):
                        if a.get("do") in ("set_flag", "clear_flag") and \
                                fk == "flag" and "flag" in a and a["flag"] not in flag_ids:
                            err(f"room {rn} event[{i}]: flag {a['flag']} not declared")
        for wp in room.get("warps", []):
            dr = wp.get("dest_room")
            if dr is not None and (not isinstance(dr, int) or not 0 <= dr < n_rooms):
                err(f"room {rn}: warp dest_room {dr!r} is not a valid room id")

    # room graph
    rg = doc.get("room_graph", {})
    sr = rg.get("start_room")
    if not isinstance(sr, int) or not (0 <= sr < max(n_rooms, 1)):
        err(f"room_graph.start_room {sr!r} is not a valid room id")

    completion = doc.get("completion", {})
    if completion.get("type") not in ("reach_goal",):
        err(f"completion.type {completion.get('type')!r} is not supported by "
            "the runtime (supported: reach_goal)")
    elif not any(r.get("goal") or "G" in "".join(r.get("tiles", []))
                 for r in rooms):
        err("completion is reach_goal but no room has a goal")

    # mapping statuses
    for where, el in iter_elements(doc):
        st = el.get("mapping_status")
        if st not in MAPPING_STATUSES:
            err(f"{where}: mapping_status {st!r} is not one of {MAPPING_STATUSES}")
            continue
        rep.status_counts[st] = rep.status_counts.get(st, 0) + 1
        if st in ("unsupported", "unknown"):
            rep.unsupported.append(where)
            msg = (f"{where}: mapping_status={st}"
                   + (f" ({el.get('notes')})" if el.get("notes") else ""))
            if allow_unsupported:
                warn(msg)
            else:
                err(msg + " — use --allow-unsupported to inspect anyway")

    # difficulty variants and bosses sections: the runtime does not implement
    # them yet; non-empty content must already carry unsupported status (the
    # loop above catches it), but guard against mislabeled entries.
    for i, dv in enumerate(doc.get("difficulty_variants", [])):
        if dv.get("mapping_status") in ("exact", "equivalent"):
            err(f"difficulty_variants[{i}]: runtime support does not exist; "
                "this cannot be marked exact/equivalent")

    return rep
