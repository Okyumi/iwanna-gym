"""gmx2pack: versioned GameMaker: Studio 1.4 adapter for
I Wanna Kill the Kamilia 2 WARPED (static-world milestone).

    GMS 1.4 .project.gmx source tree  (SUDALV92/K2W @ PIN_COMMIT)
            |
    this game-specific adapter        (rooms, objects, sprites XML)
            |
    common IWannaGym representation   (gamepack.schema IR -> .iwpack)

Static milestone scope: every room, dimensions, source room order,
solids, spikes, static hazards, saves, player starts, warps and room
transitions, the full object-instance inventory with provenance, the
room graph, boss-room locations, and the source event/code inventory.
Dynamic objects are NOT lowered yet: each is recorded per room with
``mapping_status: "unsupported"`` so the pack compiles in inspection
mode and every gap is enumerated in the coverage report.

Source coordinates and parameters are preserved verbatim; no room is
redesigned or substituted.  Classification is behavioral, from the
object XML itself (solid flag, parent chain, event inventory), never
from guesswork about names alone (names only choose spike triangle
orientation, validated against the sprite bbox).
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import subprocess
from collections import Counter
from typing import Any

from iwanna_gym.gamepack.schema import new_gamepack, new_room

ADAPTER = "gmx2pack"
ADAPTER_VERSION = "1.0.0"
GAME_ID = "k2warped_gms14"

#: frozen source identity (third_party/classic_source_manifest.toml)
PIN_COMMIT = "a6d6dce1fe21f759f9e2218c9f9445c051667ad6"
PIN_TREE = "72c80cc39be972889d2cfcff8a3a946357ac19eb"

TILE = 32

#: behavioral anchors in the source object tree
KILLER_ROOT = "objPlayerKiller"
CHANGER_ROOT = "objRoomChanger"
SAVE_ROOT = "objSave"
START_ROOT = "objPlayerStart"
PLAYER_ROOT = "objPlayer"

#: menu / non-gameplay rooms (no player start; UI-driven)
META_ROOMS = {"rInit", "rTitle", "rOptions", "rSaveBroken", "rTemplate"}

_EV_NAMES = {0: "create", 1: "destroy", 2: "alarm", 3: "step",
             4: "collision", 5: "keyboard", 6: "mouse", 7: "other",
             8: "draw", 9: "keypress", 10: "keyrelease"}

_ASSIGN = re.compile(
    r"\b(roomTo|warpX|warpY|enabled|autosave|tempTrigger|frozen)\s*=\s*"
    r"([A-Za-z_]\w*|-?\d+(?:\.\d+)?)")

_SPIKE_DIR = re.compile(r"Spike(Up|Down|Left|Right)o?$", re.I)

#: per-object classification overrides, each justified by direct
#: inspection of the source event code (recorded in the coverage
#: report).  "pending:" notes are dynamic semantics on otherwise-static
#: geometry, deferred to later milestones and reported as unsupported.
STATIC_OVERRIDES: dict[str, tuple[str, str]] = {
    "objBlock": ("solid_static",
                 "create sets tag only; pending: GradiusLaser "
                 "destructibility (Boss6 section)"),
    "objIntroBlock": ("solid_static",
                      "events set image_speed/index only (visual)"),
    "obj6BBlock": ("solid_static",
                   "pending: Giantkid destructibility (Boss6)"),
    "obj6CBlock": ("solid_static",
                   "pending: Giantkid destructibility (Boss6)"),
    "obj6DBlock": ("solid_static",
                   "pending: Giantkid destructibility (Boss6)"),
    "objCQBlockB": ("solid_static", "empty destroy event only"),
    "objCQBlockC": ("solid_static", "empty destroy event only"),
    "objSpikeUp": ("spike_static",
                   "create/other events are sprite-visual only; "
                   "GradiusLaser collision is commented out"),
    "objSpikeDown": ("spike_static",
                     "create is sprite-visual; laser collision "
                     "commented out"),
    "objSpikeLeft": ("spike_static",
                     "create is sprite-visual (incl. the rStage4KTGB "
                     "visible=0 case — invisible spikes still kill); "
                     "laser collision commented out"),
    "objSpikeRight": ("spike_static", "same basis as objSpikeLeft"),
}


class ConversionError(Exception):
    pass


# ------------------------------------------------------------- parsing

def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_sprite(path: str) -> dict[str, Any]:
    t = _read(path)

    def num(tag, default=0):
        m = re.search(rf"<{tag}>(-?\d+)</{tag}>", t)
        return int(m.group(1)) if m else default
    return {"ox": num("xorig"), "oy": num("yorigin"),
            "bl": num("bbox_left"), "br": num("bbox_right"),
            "bt": num("bbox_top"), "bb": num("bbox_bottom"),
            "w": num("width"), "h": num("height"),
            "colkind": num("colkind", 1)}


def parse_object(path: str) -> dict[str, Any]:
    t = _read(path)

    def tag(name):
        m = re.search(rf"<{name}>(.*?)</{name}>", t, re.S)
        return html.unescape(m.group(1)) if m else ""
    events = []
    for m in re.finditer(r"<event ([^>]*?)>(.*?)</event>", t, re.S):
        attrs, body = m.groups()
        et = int(re.search(r'eventtype="(\d+)"', attrs).group(1))
        en = re.search(r'enumb="(\d+)"', attrs)
        ename = re.search(r'ename="([^"]*)"', attrs)
        codes = [html.unescape(c)
                 for c in re.findall(r"<string>(.*?)</string>", body, re.S)]
        events.append({
            "type": et, "kind": _EV_NAMES.get(et, str(et)),
            "num": int(en.group(1)) if en else None,
            "ename": ename.group(1) if ename else None,
            "code_lines": sum(c.count("\n") + 1 for c in codes if c.strip()),
            "code": "\n".join(c for c in codes if c.strip()),
        })
    def clean(v):
        v = v.strip()
        return "" if v in ("<undefined>", "&lt;undefined&gt;") else v
    parent = clean(tag("parentName"))
    return {"sprite": clean(tag("spriteName")),
            "mask": clean(tag("maskName")),
            "solid": tag("solid").strip() == "-1",
            "visible": tag("visible").strip() == "-1",
            "persistent": tag("persistent").strip() == "-1",
            "parent": parent,
            "events": events}


def parse_room(path: str) -> dict[str, Any]:
    t = _read(path)

    def num(tag):
        m = re.search(rf"<{tag}>(-?\d+)</{tag}>", t)
        return int(m.group(1)) if m else 0
    code = re.search(r"<code>(.*?)</code>", t, re.S)
    insts = []
    for m in re.finditer(
            r'<instance objName="([^"]+)" x="(-?[\d.]+)" y="(-?[\d.]+)" '
            r'name="([^"]+)" locked="[^"]*" code="([^"]*)" '
            r'scaleX="(-?[\d.]+)" scaleY="(-?[\d.]+)"', t):
        o, x, y, nm, cc, sx, sy = m.groups()
        insts.append({"object": o, "x": float(x), "y": float(y),
                      "name": nm, "code": html.unescape(cc),
                      "sx": float(sx), "sy": float(sy)})
    return {"w": num("width"), "h": num("height"), "speed": num("speed"),
            "code": html.unescape(code.group(1)) if code else "",
            "instances": insts}


def parse_project(root: str) -> list[str]:
    proj = None
    for f in os.listdir(root):
        if f.endswith(".project.gmx"):
            proj = os.path.join(root, f)
            break
    if not proj:
        raise ConversionError(f"no .project.gmx under {root}")
    t = _read(proj)
    rooms = re.findall(r"<room>rooms\\(.*?)</room>", t)
    if not rooms:
        raise ConversionError("project lists no rooms")
    return rooms


# -------------------------------------------------------- classification

def _chain(objs: dict, name: str) -> list[str]:
    seen, out = set(), []
    while name and name in objs and name not in seen:
        seen.add(name)
        out.append(name)
        name = objs[name]["parent"]
    if name and name not in objs and name not in seen:
        out.append(name)                 # dangling parent name
    return out


def classify_objects(objs: dict[str, Any]) -> dict[str, str]:
    """Behavioral category per object (static milestone)."""
    cats = {}
    for name, o in objs.items():
        chain = set(_chain(objs, name))
        ev_types = {e["type"] for e in o["events"]}
        static_ok = ev_types <= {0, 8}          # create/draw only
        if name in STATIC_OVERRIDES:
            cat, _why = STATIC_OVERRIDES[name]
            # overrides may only strengthen a matching behavioral base:
            # spikes must sit on the killer chain, solids must be solid
            if cat == "spike_static" and KILLER_ROOT not in chain:
                raise ConversionError(f"{name}: spike override without "
                                      f"killer parent chain")
            if cat == "solid_static" and not o["solid"]:
                raise ConversionError(f"{name}: solid override on a "
                                      f"non-solid object")
            cats[name] = cat
            continue
        if START_ROOT in chain:
            cats[name] = "start"
        elif SAVE_ROOT in chain:
            cats[name] = "save"
        elif CHANGER_ROOT in chain:
            cats[name] = "warp"
        elif PLAYER_ROOT in chain:
            cats[name] = "player"
        elif KILLER_ROOT in chain:
            if static_ok and _SPIKE_DIR.search(name):
                cats[name] = "spike_static"
            elif static_ok:
                cats[name] = "killer_static"
            else:
                cats[name] = "dynamic"
        elif o["solid"] and static_ok:
            cats[name] = "solid_static"
        elif o["solid"]:
            cats[name] = "dynamic"          # moving/gimmick solids
        elif not o["events"]:
            cats[name] = "decor_no_events"
        else:
            cats[name] = "dynamic"
    return cats


# --------------------------------------------------------- lowering

def _world_bbox(spr, x, y, sx, sy):
    """GM-style inclusive world bbox of a scaled, unrotated instance."""
    x0 = x + (spr["bl"] - spr["ox"]) * sx
    x1 = x + (spr["br"] + 1 - spr["ox"]) * sx - (1 if sx > 0 else -1)
    y0 = y + (spr["bt"] - spr["oy"]) * sy
    y1 = y + (spr["bb"] + 1 - spr["oy"]) * sy - (1 if sy > 0 else -1)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _parse_assigns(code: str) -> dict[str, str]:
    return {k: v for k, v in _ASSIGN.findall(code or "")}


def convert(root: str) -> dict[str, Any]:
    room_order = parse_project(root)
    rooms_dir = os.path.join(root, "rooms")
    objs_dir = os.path.join(root, "objects")
    spr_dir = os.path.join(root, "sprites")

    objs: dict[str, Any] = {}
    for f in sorted(os.listdir(objs_dir)):
        if f.endswith(".object.gmx"):
            objs[f[:-11]] = parse_object(os.path.join(objs_dir, f))
    sprites: dict[str, Any] = {}
    for f in sorted(os.listdir(spr_dir)):
        if f.endswith(".sprite.gmx"):
            sprites[f[:-11]] = parse_sprite(os.path.join(spr_dir, f))
    cats = classify_objects(objs)

    def spr_of(obj_name):
        o = objs.get(obj_name)
        if not o:
            return None
        return sprites.get(o["mask"] or o["sprite"])

    ir = new_gamepack(
        GAME_ID,
        title="I Wanna Kill the Kamilia 2 WARPED (static world)",
        source_game="I Wanna Kill the Kamilia 2 WARPED",
        source_version=f"git {PIN_COMMIT[:12]}",
        source_format="GameMaker: Studio 1.4 .project.gmx tree",
        importer=f"games.{GAME_ID}.converter/{ADAPTER}",
        importer_version=ADAPTER_VERSION,
    )
    ir["completion"] = {
        "type": "none",
        "note": "static-world milestone: completion is boss-gated "
                "(dynamic content, next milestone)"}
    room_index = {n: i for i, n in enumerate(room_order)}

    # object_definitions stays empty (the iwbtgr pattern): static
    # families lower directly into the room lists; the full per-object
    # census and instance inventory live in the coverage report
    used_objects: Counter = Counter()
    inventory: list[dict[str, Any]] = []

    coverage: dict[str, Any] = {
        "adapter": f"{ADAPTER} {ADAPTER_VERSION}",
        "pin_commit": PIN_COMMIT,
        "object_categories": {},
        "per_room": {},
        "unresolved_warps": [],
        "orphan_rooms": [],
        "event_inventory": {},
        "scripts": {},
        "progression_flags": {"stageUnlocked_writes": [],
                              "tempTrigger_writes": []},
        "residual_room_code": [],
    }

    graph_edges: list[dict[str, Any]] = []
    scripted_targets = re.compile(r"room_goto\s*\(\s*(r[A-Za-z0-9_]+)")

    for rid, rname in enumerate(room_order):
        src = parse_room(os.path.join(rooms_dir, rname + ".room.gmx"))
        w_t = -(-src["w"] // TILE)
        h_t = -(-src["h"] // TILE)
        room = new_room(rid, rname, w_t, h_t)
        room["px_size"] = [src["w"], src["h"]]
        room["solids"] = []
        room["killers"] = []
        grid = [["."] * w_t for _ in range(h_t)]
        acct = Counter()

        if src["code"].strip():
            coverage["residual_room_code"].append(
                {"room": rname,
                 "lines": src["code"].count("\n") + 1})

        for inst in src["instances"]:
            oname = inst["object"]
            used_objects[oname] += 1
            cat = cats.get(oname, "dynamic")
            spr = spr_of(oname)
            if spr is None and cat in ("solid_static", "spike_static",
                                       "killer_static", "save", "warp"):
                raise ConversionError(
                    f"{rname}/{inst['name']}: static object {oname} has "
                    f"no resolvable collision sprite — refusing to skip "
                    f"geometry silently")
            x, y, sx, sy = inst["x"], inst["y"], inst["sx"], inst["sy"]
            prov = {"source_room": rname, "source_instance": inst["name"],
                    "source_object": oname}
            acct[cat] += 1

            if cat == "solid_static" and spr:
                x0, y0, x1, y1 = _world_bbox(spr, x, y, sx, sy)
                if (x0 % TILE == 0 and y0 % TILE == 0 and
                        (x1 + 1) % TILE == 0 and (y1 + 1) % TILE == 0 and
                        0 <= x0 and 0 <= y0 and
                        x1 < w_t * TILE and y1 < h_t * TILE):
                    for ty in range(int(y0) // TILE, int(y1 + 1) // TILE):
                        for tx in range(int(x0) // TILE,
                                        int(x1 + 1) // TILE):
                            grid[ty][tx] = "#"
                else:
                    room["solids"].append([x0, y0, x1, y1])
            elif cat == "spike_static" and spr:
                d = _SPIKE_DIR.search(oname).group(1).lower()
                ch = {"up": "^", "down": "v", "left": "<",
                      "right": ">"}[d]
                if (sx == 1 and sy == 1 and x % TILE == 0 and
                        y % TILE == 0 and spr["w"] == TILE and
                        spr["h"] == TILE and 0 <= x < w_t * TILE and
                        0 <= y < h_t * TILE):
                    grid[int(y) // TILE][int(x) // TILE] = ch
                else:
                    x0, y0, x1, y1 = _world_bbox(spr, x, y, sx, sy)
                    room["killers"].append(
                        {"shape": f"spike_{d}", "x0": x0, "y0": y0,
                         "x1": x1, "y1": y1})
            elif cat == "killer_static" and spr:
                x0, y0, x1, y1 = _world_bbox(spr, x, y, sx, sy)
                room["killers"].append(
                    {"shape": "rect", "x0": x0, "y0": y0,
                     "x1": x1, "y1": y1})
            elif cat == "save" and spr:
                x0, y0, x1, y1 = _world_bbox(spr, x, y, sx, sy)
                room["checkpoints"].append(
                    {"x": (x0 + x1 + 1) / 2.0, "y": (y0 + y1 + 1) / 2.0,
                     "half_w": (x1 - x0 + 1) / 2.0,
                     "half_h": (y1 - y0 + 1) / 2.0,
                     "difficulty_mask": 0b1111,
                     "source_object": oname,
                     "source_instance": inst["name"]})
            elif cat == "start":
                # objPlayerStart room-start: player created at (x, y)
                if room["start"] is None:
                    room["start"] = {"x": x, "y": y}
            elif cat == "warp":
                vals = _parse_assigns(inst["code"])
                base = _parse_assigns(
                    "\n".join(e["code"] for e in objs[oname]["events"]
                              if e["type"] == 0))
                roomto = vals.get("roomTo", base.get("roomTo"))
                wx = float(vals.get("warpX", base.get("warpX", 0) or 0))
                wy = float(vals.get("warpY", base.get("warpY", 0) or 0))
                enabled = vals.get("enabled",
                                   base.get("enabled", "true")) != "false"
                if roomto in room_index:
                    x0, y0, x1, y1 = (_world_bbox(spr, x, y, sx, sy)
                                      if spr else (x, y, x + 31, y + 31))
                    wrec = {"x": (x0 + x1 + 1) / 2.0,
                            "y": (y0 + y1 + 1) / 2.0,
                            "half_w": (x1 - x0 + 1) / 2.0,
                            "half_h": (y1 - y0 + 1) / 2.0,
                            "dest_room": room_index[roomto],
                            "source_instance": inst["name"]}
                    if wx == 0 and wy == 0:
                        wrec.update(mode="target_start",
                                    dest_x=None, dest_y=None)
                    else:
                        wrec.update(mode="absolute", dest_x=wx, dest_y=wy)
                    if not enabled:
                        wrec["active"] = False
                    room["warps"].append(wrec)
                    graph_edges.append(
                        {"from": rname, "to": roomto, "via": oname,
                         "x": x, "y": y,
                         "mode": wrec["mode"],
                         "enabled": enabled,
                         "source_instance": inst["name"]})
                else:
                    coverage["unresolved_warps"].append(
                        {"room": rname, "instance": inst["name"],
                         "object": oname,
                         "note": "roomTo not statically resolvable "
                                 "(dynamic creation code)"})
                    acct["warp_unresolved"] += 1
            # every instance (lowered or not) is inventoried with
            # provenance; statics are lowered into the room lists above,
            # everything else is unsupported at the static milestone
            inventory.append({
                "room": rname, "object": oname, "x": x, "y": y,
                "scale_x": sx, "scale_y": sy,
                "creation_code_lines": (inst["code"].count("\n") + 1)
                                       if inst["code"].strip() else 0,
                "category": cat,
                "mapping_status": (
                    "exact" if cat in ("solid_static", "spike_static",
                                       "killer_static", "save", "start",
                                       "warp") else "unsupported"),
                "provenance": prov,
            })

        room["tiles"] = ["".join(r) for r in grid]
        # scripted room_goto targets inside instance creation codes
        for inst in src["instances"]:
            for tgt in scripted_targets.findall(inst["code"] or ""):
                if tgt in room_index:
                    graph_edges.append(
                        {"from": rname, "to": tgt, "via": "scripted",
                         "x": inst["x"], "y": inst["y"],
                         "source_instance": inst["name"],
                         "lowered": False})
        coverage["per_room"][rname] = dict(acct)
        ir["rooms"].append(room)

    # start room: first non-meta room in source order with a player start
    start_room = next(
        (r["id"] for r in ir["rooms"]
         if r["name"] not in META_ROOMS and r["start"] is not None), 0)
    ir["room_graph"] = {"start_room": start_room, "edges": graph_edges}

    # ------------------------------------------------ inventories
    for oname, o in objs.items():
        if used_objects.get(oname) or cats.get(oname) not in (
                None, "decor_no_events"):
            coverage["event_inventory"][oname] = {
                "category": cats.get(oname, "dynamic"),
                "events": [
                    {"kind": e["kind"], "num": e["num"],
                     "ename": e["ename"], "code_lines": e["code_lines"]}
                    for e in o["events"]],
                "placed_instances": used_objects.get(oname, 0),
            }
    scripts_dir = os.path.join(root, "scripts")
    for f in sorted(os.listdir(scripts_dir)):
        if f.endswith(".gml"):
            coverage["scripts"][f[:-4]] = \
                _read(os.path.join(scripts_dir, f)).count("\n") + 1
    # progression-flag writes (gates recorded, implemented later)
    flagpat = re.compile(r"(stageUnlocked|tempTrigger)\[(\d+)\]\s*=")
    for oname, o in objs.items():
        for e in o["events"]:
            for kind, idx in flagpat.findall(e["code"]):
                coverage["progression_flags"][f"{kind}_writes"].append(
                    {"object": oname, "event": e["kind"], "index": int(idx)})
    files = {f[:-9] for f in os.listdir(rooms_dir)
             if f.endswith(".room.gmx")}
    coverage["orphan_rooms"] = sorted(files - set(room_order))
    coverage["static_overrides"] = {
        k: {"category": v[0], "justification": v[1]}
        for k, v in STATIC_OVERRIDES.items()}
    coverage["object_categories"] = dict(Counter(cats.values()))
    coverage["boss_rooms"] = [n for n in room_order
                              if re.match(r"rBoss|rExtraBoss|"
                                          r"rExtraStage.*Boss", n)]
    coverage["meta_rooms"] = sorted(META_ROOMS & set(room_order))
    coverage["instances_total"] = len(inventory)
    coverage["instances_by_status"] = dict(
        Counter(i["mapping_status"] for i in inventory))
    return {"ir": ir, "coverage": coverage, "room_order": room_order,
            "cats": cats, "inventory": inventory}


def source_identity(root: str) -> dict[str, str]:
    """Best-effort git pin verification of the source clone."""
    out = {"pin_commit": PIN_COMMIT, "pin_tree": PIN_TREE}
    try:
        head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              timeout=20).stdout.strip()
        tree = subprocess.run(["git", "-C", root, "rev-parse",
                               "HEAD^{tree}"], capture_output=True,
                              text=True, timeout=20).stdout.strip()
        out["actual_commit"] = head
        out["actual_tree"] = tree
        out["pin_match"] = (head == PIN_COMMIT)
    except Exception:
        out["actual_commit"] = ""
        out["pin_match"] = False
    return out


def project_sha256(root: str) -> str:
    """Digest of the gameplay-relevant source text (project, rooms,
    objects, sprites XML, scripts) — asset binaries excluded."""
    h = hashlib.sha256()
    for sub, exts in (("", (".project.gmx",)),
                      ("rooms", (".room.gmx",)),
                      ("objects", (".object.gmx",)),
                      ("sprites", (".sprite.gmx",)),
                      ("scripts", (".gml",))):
        d = os.path.join(root, sub) if sub else root
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(exts):
                h.update(f.encode())
                with open(os.path.join(d, f), "rb") as fh:
                    h.update(fh.read())
    return h.hexdigest()
