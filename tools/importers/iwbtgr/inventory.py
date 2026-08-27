"""Machine-readable inventory of an IWBTGR gm82save source tree.

Produces the coverage report (build/source_reports/iwbtgr_1_5_3.json) and
the three generated docs. The committed report contains METADATA ONLY —
positions, dimensions, names, counts, hashes, event signatures — never
GML bodies, sprites, or audio (third_party/SOURCES.md). Full code bodies
can be dumped locally with ``with_code=True`` (kept out of git).

Original numeric values are preserved verbatim; nothing is snapped to a
tile grid.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from typing import Any

from . import mapping
from .gm82 import Gm82Project, _sha256_text, load_project

_ROOM_GOTO = re.compile(r"room_goto(?:_fixed)?\s*\(\s*([A-Za-z_]\w*)")
_ROOM_GOTO_REL = re.compile(r"room_goto_(next|previous)\b")
_GLOBAL = re.compile(r"global\.([A-Za-z_]\w*)")
_MOD_MARKERS = ("autosplitter",)
#: known warp-configuration statements in instance creation code
#: (consumed by objects/warp.gml: `if (roomTo!=0) room_goto(roomTo)` etc.)
_WARP_ASSIGN = re.compile(
    r"\b(roomTo|warpX|warpY|warpXhoff|warpYvoff)\s*=\s*"
    r"([A-Za-z_]\w*|-?\d+(?:\.\d+)?)")


def _parse_warp_assigns(code: str) -> dict[str, Any]:
    """Parse the known warp-target statements (a mechanical parse of source
    statements — no interpretation of arbitrary GML)."""
    out: dict[str, Any] = {}
    for key, val in _WARP_ASSIGN.findall(code):
        try:
            out[key] = float(val) if "." in val else int(val)
        except ValueError:
            out[key] = val          # a room (or other) identifier
    return out


def tree_sha256(root: str) -> str:
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in sorted(os.walk(root)):
        dirnames.sort()
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def _git_provenance(root: str) -> dict[str, Any]:
    def run(*args):
        try:
            return subprocess.run(["git", "-C", root, *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        except Exception:
            return None
    commit = run("rev-parse", "HEAD")
    if not commit:
        return {}
    return {"git_commit": commit,
            "git_remote": run("config", "--get", "remote.origin.url")}


def _code_refs(text: str):
    gotos = sorted(set(_ROOM_GOTO.findall(text)))
    rel = sorted(set(_ROOM_GOTO_REL.findall(text)))
    return gotos, rel


def _mod_delta(proj: Gm82Project) -> dict[str, list[str]]:
    """Files/objects touched by the autosplitter mod (marker-based; the
    authoritative delta is a diff against the official source zip, pending
    — see the report's `source.mod` section)."""
    scripts = [n for n, code in proj.scripts.items()
               if any(m in code.lower() for m in _MOD_MARKERS)
               or any(m in n.lower() for m in _MOD_MARKERS)]
    objects = [n for n, o in proj.objects.items()
               if any(any(m in e.code.lower() for m in _MOD_MARKERS)
                      for e in o.events)]
    return {"scripts": sorted(scripts), "objects": sorted(objects)}


def build_inventory(root: str, with_code: bool = False) -> dict[str, Any]:
    proj = load_project(root)
    mod = _mod_delta(proj)
    mod_objects = set(mod["objects"])

    # ---- usage ----
    inst_count: Counter[str] = Counter()
    rooms_used: dict[str, set] = defaultdict(set)
    for rname, room in proj.rooms.items():
        for inst in room.instances:
            inst_count[inst.object] += 1
            rooms_used[inst.object].add(rname)

    # ---- objects ----
    objects_out = []
    globals_usage: Counter[str] = Counter()
    for name in sorted(proj.objects):
        o = proj.objects[name]
        cls = mapping.classify_object(name, o, proj, rooms_used.get(name, set()),
                                      name in mod_objects)
        events_out = []
        obj_gotos: set[str] = set()
        for e in o.events:
            gotos, rel = _code_refs(e.code)
            obj_gotos.update(gotos)
            for g in _GLOBAL.findall(e.code):
                globals_usage[g] += 1
            ev = {"name": e.name, "lines": e.lines, "sha256": e.sha256,
                  "status": "preserved_metadata"}
            if gotos or rel:
                ev["room_goto"] = gotos + [f"room_goto_{r}" for r in rel]
            if with_code:
                ev["code"] = e.code
            events_out.append(ev)
        objects_out.append({
            "name": name,
            "sprite": o.sprite, "mask": o.mask or o.sprite,
            "visible": o.visible, "solid": o.solid,
            "persistent": o.persistent, "depth": o.depth,
            "parent": o.parent, "parent_chain": proj.parent_chain(name),
            "instance_count": inst_count.get(name, 0),
            "rooms_used": sorted(rooms_used.get(name, ())),
            "events": events_out,
            "event_count": len(events_out),
            "room_goto_targets": sorted(obj_gotos),
            "semantic": cls,
        })
    status_of = {o["name"]: o["semantic"]["status"] for o in objects_out}

    # ---- rooms ----
    rooms_out = []
    warp_edges: list[dict[str, Any]] = []
    total_instances = 0
    total_tiles = 0
    for idx, rname in enumerate(proj.room_order or sorted(proj.rooms)):
        room = proj.rooms[rname]
        code_gotos, code_rel = _code_refs(room.creation_code)
        for g in _GLOBAL.findall(room.creation_code):
            globals_usage[g] += 1
        insts_out = []
        by_object: Counter[str] = Counter()
        inst_gotos: set[str] = set()
        unsupported_n = 0
        for inst in room.instances:
            by_object[inst.object] += 1
            if status_of.get(inst.object) == "unsupported":
                unsupported_n += 1
            row: dict[str, Any] = {
                "object": inst.object, "x": inst.x, "y": inst.y,
                "id": inst.id_hex,
            }
            if inst.xscale != 1 or inst.yscale != 1:
                row["xscale"], row["yscale"] = inst.xscale, inst.yscale
            if inst.angle:
                row["angle"] = inst.angle
            if inst.blend != 4294967295:
                row["blend"] = inst.blend
            if inst.creation_code is not None:
                gotos, rel = _code_refs(inst.creation_code)
                inst_gotos.update(gotos)
                for g in _GLOBAL.findall(inst.creation_code):
                    globals_usage[g] += 1
                row["creation_code"] = {
                    "lines": len(inst.creation_code.splitlines()),
                    "sha256": _sha256_text(inst.creation_code),
                    "status": "preserved_metadata",
                }
                if gotos or rel:
                    row["creation_code"]["room_goto"] = (
                        gotos + [f"room_goto_{r}" for r in rel])
                warp = _parse_warp_assigns(inst.creation_code)
                if warp:
                    row["parsed_warp"] = warp
                    row["creation_code"]["status"] = "partially_parsed"
                    if isinstance(warp.get("roomTo"), str):
                        warp_edges.append({
                            "from": rname, "to": warp["roomTo"], "via": "warp",
                            "object": inst.object,
                            "x": inst.x, "y": inst.y,
                            "dest": {k: warp[k] for k in
                                     ("warpX", "warpY", "warpXhoff", "warpYvoff")
                                     if k in warp},
                        })
                if with_code:
                    row["creation_code"]["code"] = inst.creation_code
            insts_out.append(row)
        transition_objects = sorted(
            obj for obj in by_object
            if any(o["name"] == obj and o["room_goto_targets"]
                   for o in objects_out))
        tiles_blob = "".join(
            f"{t.background},{t.x},{t.y},{t.u},{t.v},{t.width},{t.height},"
            f"{t.depth},{t.xscale},{t.yscale},{t.blend}\n"
            for t in room.tiles)
        rooms_out.append({
            "name": rname,
            "order_index": idx,
            "width": room.width, "height": room.height,
            "speed": room.speed,
            "snap_x": room.settings.get("snap_x"),
            "snap_y": room.settings.get("snap_y"),
            "persistent": room.settings.get("roompersistent"),
            "views": room.views,
            "backgrounds": room.backgrounds,
            "creation_code": {
                "lines": len(room.creation_code.splitlines()),
                "sha256": _sha256_text(room.creation_code),
                "room_goto": code_gotos + [f"room_goto_{r}" for r in code_rel],
                "status": "preserved_metadata",
                **({"code": room.creation_code} if with_code else {}),
            },
            "tile_layers": {str(k): v for k, v in sorted(room.tile_layers.items())},
            "tile_count": len(room.tiles),
            "tiles_sha256": _sha256_text(tiles_blob),
            "instance_count": len(room.instances),
            "instances_by_object": dict(by_object.most_common()),
            "unsupported_instance_count": unsupported_n,
            "transitions": {
                "room_code_targets": code_gotos,
                "instance_code_targets": sorted(inst_gotos),
                "warp_targets": sorted({e["to"] for e in warp_edges
                                        if e["from"] == rname}),
                "transition_capable_objects_present": transition_objects,
            },
            "instances": insts_out,
        })
        total_instances += len(room.instances)
        total_tiles += len(room.tiles)

    # ---- scripts / assets ----
    scripts_out = [{"name": n, "lines": len(c.splitlines()),
                    "sha256": _sha256_text(c),
                    "mod_added": n in set(mod["scripts"]),
                    **({"code": c} if with_code else {})}
                   for n, c in sorted(proj.scripts.items())]
    for c in proj.scripts.values():
        for g in _GLOBAL.findall(c):
            globals_usage[g] += 1

    def asset_meta(d):
        return [{"name": s.name, "frames": s.frame_count,
                 "origin": [s.props.get("origin_x"), s.props.get("origin_y")],
                 "bbox": [s.props.get("bbox_left"), s.props.get("bbox_top"),
                          s.props.get("bbox_right"), s.props.get("bbox_bottom")],
                 "collision_shape": s.props.get("collision_shape"),
                 "per_frame_colliders": s.props.get("per_frame_colliders"),
                 "size": [s.width, s.height],
                 "frame_sha256": s.frame_sha256,
                 "payload_committed": False}
                for s in (d[k] for k in sorted(d))]

    statuses = Counter(o["semantic"]["status"] for o in objects_out)

    report = {
        "report_format": "iwbtgr_inventory/1",
        "source": {
            "game": "I Wanna Be The Guy: Remastered",
            "version_of_record": "1.5.3",
            "project_settings": {
                k: proj.settings.get(k) for k in
                ("gm82_version", "gameid", "info_author", "info_version",
                 "exe_description", "exe_version")},
            "format": "GameMaker 8.2 gm82save text tree",
            "root": os.path.abspath(root),
            "tree_sha256": tree_sha256(root),
            **_git_provenance(root),
            "official_package": {
                "name": "IWBTGR Source 1.5.3.zip",
                "location": "https://cherry-treehouse.itch.io/iwbtgr",
                "checksum_status": "pending — not downloadable from this "
                                   "environment; diff against it when available",
            },
            "mod": {
                "note": "this tree is the speedrun-community autosplitter mod "
                        "of the 1.5.3 source (marker-detected delta below); "
                        "mod elements are excluded from gameplay mapping",
                "marker_detected_delta": mod,
            },
        },
        "cross_reference": {
            "original_iwbtg_2007": {
                "status": "pending",
                "reason": "the released MMF2 .mfa source (kayin.moe) is not "
                          "reachable from this environment; no original-vs-"
                          "remastered content diff has been performed. Known "
                          "documented differences (docs/fidelity_contract.md): "
                          "Remastered uses Yuuutu GM8 physics with variable "
                          "jump height; the original has two fixed jump "
                          "heights and MMF2 frame pacing.",
            },
        },
        "counts": {
            "rooms": len(rooms_out),
            "object_definitions": len(objects_out),
            "object_instances": total_instances,
            "tiles": total_tiles,
            "scripts": len(scripts_out),
            "sprites": len(proj.sprites),
            "backgrounds": len(proj.backgrounds),
            "paths": len(proj.paths),
            "fonts": len(proj.fonts),
            "datafiles": len(proj.datafiles),
            "objects_by_status": dict(statuses),
            "instances_by_status": dict(Counter(
                status_of.get(i["object"], "unsupported")
                for r in rooms_out for i in r["instances"])),
        },
        "code_coverage": {
            "object_events_total": sum(o["event_count"] for o in objects_out),
            "object_events_preserved_metadata":
                sum(o["event_count"] for o in objects_out),
            "object_events_parsed_to_ir": 0,
            "instance_codes_partially_parsed": sum(
                1 for r in rooms_out for i in r["instances"]
                if "parsed_warp" in i),
            "instance_creation_codes": sum(
                1 for r in rooms_out for i in r["instances"]
                if "creation_code" in i),
            "room_creation_codes": sum(
                1 for r in rooms_out if r["creation_code"]["lines"] > 0),
            "note": "every event and creation code is inventoried with hash "
                    "and line count (nothing dropped); statement-level "
                    "parsing into the canonical event IR is the conversion "
                    "milestone, not this one",
        },
        "global_variables": dict(globals_usage.most_common()),
        "room_graph": {
            "start_room": (proj.room_order or [None])[0],
            "warp_edges": warp_edges,
            "note": "edges parsed mechanically from warp-instance creation "
                    "code (roomTo=/warpX=/warpY= statements consumed by "
                    "objects/warp.gml); scripted transitions inside object "
                    "events (bosses, endings) are inventoried via each "
                    "object's room_goto_targets",
        },
        "rooms": rooms_out,
        "objects": objects_out,
        "scripts": scripts_out,
        "sprites": asset_meta(proj.sprites),
        "backgrounds_assets": asset_meta(proj.backgrounds),
        "triggers": sorted(proj.triggers),
        "paths_list": proj.paths,
        "fonts_list": proj.fonts,
        "datafiles_list": proj.datafiles,
    }
    return report


def save_report(report: dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, sort_keys=False)
        f.write("\n")


# ---------------------------------------------------------------- docs

_GEN = ("<!-- GENERATED by `python -m tools.iwimport inventory` from the "
        "locally supplied IWBTGR source tree — do not hand-edit. -->")


def doc_source_inventory(rep: dict[str, Any]) -> str:
    s, c, cov = rep["source"], rep["counts"], rep["code_coverage"]
    lines = [_GEN, "", "# IWBTGR 1.5.3 source inventory", ""]
    lines += [
        f"Source of record: **{s['game']} {s['version_of_record']}** "
        f"(`exe_version={s['project_settings'].get('exe_version')}`, "
        f"`gameid={s['project_settings'].get('gameid')}`), "
        f"format: {s['format']}.",
        "",
        f"Extraction input: `{s.get('git_remote') or s['root']}`"
        + (f" @ `{s.get('git_commit', '')[:12]}`" if s.get("git_commit") else "")
        + f", tree sha256 `{s['tree_sha256'][:16]}…`. "
        "This tree is the speedrun-community **autosplitter mod** of the "
        "author-released source; marker-detected mod delta: scripts "
        f"{s['mod']['marker_detected_delta']['scripts']}, objects "
        f"{s['mod']['marker_detected_delta']['objects'] or 'none'} "
        "(excluded from gameplay mapping). The official "
        f"`{s['official_package']['name']}` from "
        f"{s['official_package']['location']} remains the package of record; "
        "its checksum/diff is pending (not downloadable from the build "
        "environment).", "",
        "## Counts", "",
        f"- rooms: **{c['rooms']}** (every source room inventoried)",
        f"- object definitions: **{c['object_definitions']}**",
        f"- object instances: **{c['object_instances']}** "
        "(each with verbatim source coordinates)",
        f"- tiles: **{c['tiles']}** across per-depth layers",
        f"- scripts: **{c['scripts']}**; sprites: {c['sprites']}; "
        f"backgrounds: {c['backgrounds']}; paths: {c['paths']}; "
        f"fonts: {c['fonts']}; datafiles: {c['datafiles']}",
        "",
        "## Mapping status (objects)", "",
    ]
    for k in mapping.STATUSES:
        lines.append(f"- {k}: {c['objects_by_status'].get(k, 0)} objects, "
                     f"{c['instances_by_status'].get(k, 0)} placed instances")
    lines += [
        "", "## Code coverage", "",
        f"- object events inventoried: {cov['object_events_total']} "
        "(100% preserved as metadata: name, line count, sha256)",
        f"- events parsed to canonical IR: {cov['object_events_parsed_to_ir']} "
        "(conversion milestone)",
        f"- instance creation codes: {cov['instance_creation_codes']} "
        "(hashed; `room_goto` targets extracted)",
        f"- rooms with creation code: {cov['room_creation_codes']}",
        f"- {cov['note']}", "",
        "## Global variables (top 30 by references)", "",
    ]
    for name, n in list(rep["global_variables"].items())[:30]:
        lines.append(f"- `global.{name}` × {n}")
    lines += [
        "", "## Original-IWBTG cross-reference", "",
        rep["cross_reference"]["original_iwbtg_2007"]["reason"], "",
        "Machine-readable report: `build/source_reports/iwbtgr_1_5_3.json`. "
        "Asset payloads (sprites/audio) are NOT committed — metadata and "
        "checksums only (third_party/SOURCES.md).",
    ]
    return "\n".join(lines) + "\n"


def doc_object_mapping(rep: dict[str, Any]) -> str:
    lines = [_GEN, "", "# IWBTGR object mapping", "",
             "Statuses: exact / equivalent / unsupported / irrelevant (to "
             "gameplay) / visual_audio_only — assigned mechanically by "
             "`tools/importers/iwbtgr/mapping.py` (rule recorded per row).", "",
             "| source object | instances | rooms used | semantic type | "
             "status | rule | notes |",
             "|---|---|---|---|---|---|---|"]
    for o in sorted(rep["objects"],
                    key=lambda o: (-o["instance_count"], o["name"])):
        sem = o["semantic"]
        rooms = ", ".join(o["rooms_used"][:4])
        if len(o["rooms_used"]) > 4:
            rooms += f", +{len(o['rooms_used']) - 4}"
        notes = sem["notes"].replace("|", "/")
        lines.append(
            f"| {o['name']} | {o['instance_count']} | {rooms or '—'} | "
            f"{sem['semantic']} | {sem['status']} | {sem['rule']} | {notes} |")
    return "\n".join(lines) + "\n"


def doc_room_inventory(rep: dict[str, Any]) -> str:
    lines = [_GEN, "", "# IWBTGR room inventory", "",
             "Room order is the source resource-tree order. Transition counts "
             "are `room_goto` targets found in room/instance creation code; "
             "`t-objs` counts placed object types whose events contain "
             "`room_goto` (shared logic, e.g. warps/doors).", "",
             "| # | source room | dimensions | speed | tiles | instances | "
             "warp transitions to | t-objs | unsupported instances |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rep["rooms"]:
        tr = r["transitions"]
        code_t = sorted(set(tr["room_code_targets"]) |
                        set(tr["instance_code_targets"]) |
                        set(tr.get("warp_targets", ())))
        lines.append(
            f"| {r['order_index']} | {r['name']} | "
            f"{r['width']}×{r['height']} | {r['speed']} | {r['tile_count']} | "
            f"{r['instance_count']} | "
            f"{', '.join(code_t) or '—'} | "
            f"{len(tr['transition_capable_objects_present'])} | "
            f"{r['unsupported_instance_count']} |")
    lines += ["", "Every room, every instance, and every tile layer appears "
              "in `build/source_reports/iwbtgr_1_5_3.json` with verbatim "
              "source coordinates (no tile-grid snapping)."]
    return "\n".join(lines) + "\n"
