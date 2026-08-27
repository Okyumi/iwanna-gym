"""Importer for the synthetic source format ("synthsrc/1").

This is the reference extractor and the committed test vehicle for the
pipeline (tests/fixtures/). The format deliberately mimics a generic
editor export — a project file plus per-room JSON with object instances
and simple declarative events — so the extractor exercises the same
concerns a real GameMaker/MMF importer will face: object mapping tables,
px-coordinate instances, per-element provenance, and honest handling of
objects it does not recognize (mapping_status="unknown", never a guess).
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from iwanna_gym.gamepack.schema import TILE_PX, new_gamepack, new_room

NAME = "synthetic"
VERSION = "1.0"

#: source object -> (canonical kind, mapping_status, notes)
OBJECT_MAP = {
    "sBlock":          ("tile_block", "exact", ""),
    "sSpikeUp":        ("tile_spike_up", "exact", ""),
    "sSpikeDown":      ("tile_spike_down", "exact", ""),
    "sSpikeLeft":      ("tile_spike_left", "exact", ""),
    "sSpikeRight":     ("tile_spike_right", "exact", ""),
    "sGoal":           ("tile_goal", "exact", ""),
    "sPlayerStart":    ("player_start", "exact", ""),
    "sSave":           ("save", "exact", ""),
    "sWarp":           ("warp", "exact", ""),
    "sGate":           ("gate", "exact", ""),
    "sMovingPlatform": ("platform", "equivalent",
                        "source oscillates between two px endpoints; runtime "
                        "expresses the same motion as range around the spawn "
                        "point (identical trajectory for symmetric paths)"),
}

#: source event type -> handler building canonical events
EVENT_TYPES = ("region_flag", "flag_gate_open")


def detect(path: str) -> bool:
    pj = os.path.join(path, "project.json")
    if not os.path.isfile(pj):
        return False
    with open(pj, encoding="utf-8") as f:
        return json.load(f).get("format") == "synthsrc/1"


def _checksum(path: str) -> str:
    h = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(path)):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            h.update(os.path.relpath(p, path).encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def extract(path: str, game_id: str | None = None) -> dict[str, Any]:
    with open(os.path.join(path, "project.json"), encoding="utf-8") as f:
        proj = json.load(f)
    if proj.get("format") != "synthsrc/1":
        raise ValueError(f"{path}: not a synthsrc/1 project")

    doc = new_gamepack(
        game_id or proj["name"].lower().replace(" ", "_"),
        title=proj.get("name", ""),
        source_game=proj.get("name", ""),
        source_version=proj.get("version", ""),
        source_format="synthsrc/1",
        importer=NAME,
        importer_version=VERSION,
    )
    doc["provenance"]["source_checksum_sha256"] = _checksum(path)
    flags = dict(proj.get("flags", {}))          # name -> id
    doc["global_flags"] = [
        {"id": fid, "name": fname,
         "provenance": {"source_game": proj.get("name", "")}}
        for fname, fid in sorted(flags.items(), key=lambda kv: kv[1])
    ]

    used_objects: set[str] = set()
    unknown_objects: set[str] = set()

    room_dir = os.path.join(path, "rooms")
    room_files = sorted(f for f in os.listdir(room_dir) if f.endswith(".json"))
    srcrooms = []
    for fn in room_files:
        with open(os.path.join(room_dir, fn), encoding="utf-8") as f:
            srcrooms.append(json.load(f))
    name_to_id = {r["name"]: i for i, r in enumerate(srcrooms)}

    for rid, sr in enumerate(srcrooms):
        w = int(sr["width"]) // TILE_PX
        h = int(sr["height"]) // TILE_PX
        room = new_room(rid, sr["name"], w, h)
        prov_room = {"source_game": proj.get("name", ""),
                     "source_version": proj.get("version", ""),
                     "source_room": sr["name"]}

        grid = [list(row) for row in room["tiles"]]
        for inst in sr.get("instances", []):
            oname = inst["object"]
            used_objects.add(oname)
            prov = dict(prov_room, source_object=oname,
                        source_instance=inst.get("id"))
            mapped = OBJECT_MAP.get(oname)
            if mapped is None:
                unknown_objects.add(oname)
                room["instances"].append({
                    "object": oname,
                    "x": inst["x"], "y": inst["y"],
                    "params": dict(inst.get("params", {})),
                    "mapping_status": "unknown",
                    "notes": f"source object {oname!r} is not in the importer's "
                             "mapping table",
                    "provenance": prov,
                })
                continue
            kind, status, notes = mapped
            if kind.startswith("tile_"):
                tx, ty = int(inst["x"]) // TILE_PX, int(inst["y"]) // TILE_PX
                ch = {"tile_block": "#", "tile_spike_up": "^",
                      "tile_spike_down": "v", "tile_spike_left": "<",
                      "tile_spike_right": ">", "tile_goal": "G"}[kind]
                rx = int(inst.get("repeat_x", 1))
                ry = int(inst.get("repeat_y", 1))
                for dy in range(max(ry, 1)):
                    for dx in range(max(rx, 1)):
                        if 0 <= tx + dx < w and 0 <= ty + dy < h:
                            grid[ty + dy][tx + dx] = ch
                continue
            if kind == "player_start":
                room["start"] = {"x": inst["x"] + TILE_PX / 2,
                                 "y": inst["y"] + (TILE_PX - 1) - 8}
                continue
            params = dict(inst.get("params", {}))
            if kind == "warp" and isinstance(params.get("dest_room"), str):
                params["dest_room"] = name_to_id[params["dest_room"]]
                # source stores destinations as top-left px; canonical wants
                # the player origin position
                params["dest_x"] = params.get("dest_x", 0) + TILE_PX / 2
                params["dest_y"] = params.get("dest_y", 0) + (TILE_PX - 1) - 8
            if kind == "platform" and "x2" in params:
                # endpoint-pair oscillation -> center + range (the documented
                # equivalence in OBJECT_MAP)
                x0px = inst["x"] + TILE_PX / 2
                x1px = params.pop("x2") + TILE_PX / 2
                center = (x0px + x1px) / 2.0
                params["range"] = abs(x1px - x0px) / 2.0
                inst = dict(inst, x=center - TILE_PX / 2)
                params.setdefault("vx", 1.0)
            room["instances"].append({
                "object": oname,
                "x": inst["x"] + TILE_PX / 2, "y": inst["y"] + TILE_PX / 2,
                "tag": inst.get("tag", 0),
                "params": params,
                "mapping_status": status,
                "notes": notes,
                "provenance": prov,
            })
        room["tiles"] = ["".join(r) for r in grid]

        for ev in sr.get("events", []):
            prov = dict(prov_room, source_event=ev.get("id"))
            et = ev.get("type")
            if et == "region_flag":
                room["events"].append({
                    "when": "enter_region",
                    "x0": ev["x0"], "y0": ev["y0"],
                    "x1": ev["x1"], "y1": ev["y1"],
                    "once": True,
                    "actions": [{"do": "set_flag", "id": flags[ev["flag"]]}],
                    "mapping_status": "exact",
                    "provenance": prov,
                })
            elif et == "flag_gate_open":
                room["events"].append({
                    "when": "flag_set", "flag": flags[ev["flag"]],
                    "once": True,
                    "actions": [{"do": "open_gate", "tag": ev["gate"]}],
                    "mapping_status": "exact",
                    "provenance": prov,
                })
            else:
                room["events"].append({
                    "when": str(et),
                    "actions": [],
                    "mapping_status": "unknown",
                    "notes": f"source event type {et!r} is not in the "
                             "importer's mapping table",
                    "provenance": prov,
                })

        edges = sr.get("edges", {}) or {}
        room["edges"] = {
            k: (name_to_id[v] if isinstance(v, str) else v)
            for k, v in {e: edges.get(e) for e in
                         ("left", "right", "up", "down")}.items()
        }
        doc["rooms"].append(room)

    # object definitions for everything the source used
    for oname in sorted(used_objects):
        if oname in OBJECT_MAP:
            kind, status, notes = OBJECT_MAP[oname]
            mask = ("spike_triangle" if "spike" in kind or kind == "trap"
                    else "rect")
            doc["object_definitions"].append({
                "name": oname, "kind": kind, "collision_mask": mask,
                "mapping_status": status, "notes": notes,
                "provenance": {"source_object": oname},
            })
        else:
            doc["object_definitions"].append({
                "name": oname, "kind": None, "collision_mask": None,
                "mapping_status": "unknown",
                "notes": "not in the importer's mapping table",
                "provenance": {"source_object": oname},
            })

    doc["room_graph"]["start_room"] = name_to_id[proj["start_room"]]
    doc["room_graph"]["edges"] = _derive_graph(doc)
    goal_room = next((r["id"] for r in doc["rooms"]
                      if r.get("goal") or "G" in "".join(r["tiles"])), None)
    doc["completion"] = {"type": "reach_goal", "room": goal_room}
    return doc


def _derive_graph(doc: dict[str, Any]) -> list[list]:
    edges = []
    for room in doc["rooms"]:
        for inst in room["instances"]:
            if inst.get("mapping_status") in ("unsupported", "unknown"):
                continue
            params = inst.get("params", {})
            if inst["object"] == "sWarp" and params.get("dest_room") is not None:
                edges.append([room["id"], params["dest_room"], "warp"])
        for side, tgt in room["edges"].items():
            if tgt is not None:
                edges.append([room["id"], tgt, f"edge_{side}"])
    return edges
