"""IWBTGR 1.5.3 static-world converter: gm82save source tree -> canonical IR.

Imports the COMPLETE static world structure mechanically from the source:
every room (exact pixel dimensions), all solid geometry (tile-exact where
tile-aligned, pixel-exact rect solids otherwise), all spikes (standard
triangle masks; odd-positioned ones as pixel-exact killer records), all
killer blocks, every difficulty-gated save, every warp (per-axis
destination semantics parsed from the exact statements warp.gml consumes),
the player start of each room, and the conditional/side-effect structure
of transitions. Dynamic objects are NOT imported here — they are excluded
visibly and enumerated in the coverage report (this milestone is the
static world; see docs/iwbtgr_room_graph.md).

NOTHING in this module hand-designs geometry: every coordinate flows from
the parsed source files, and the tests assert the conversion reconciles
with an independent recount of the source.
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from typing import Any

from iwanna_gym.gamepack.schema import new_gamepack, new_room

GAME_ID = "iwbtgr_1_5_3"
CONVERTER_VERSION = "1.0"
TILE = 32

#: gameplay progression flags (global flag ids used for conditional routes)
PROGRESSION_FLAGS = {
    "orb_tyson": 1, "orb_birdo": 2, "orb_kraidgief": 3, "orb_bowser": 4,
    "orb_mother": 5, "orb_dracula": 6, "orb_dragon": 7, "orb_guy": 8,
}

#: rooms that are menus/meta, not part of the playable world route
META_ROOMS = {"rInit", "rTitle", "rFiles", "rUnlocks", "rCredits",
              "rBossRush", "rDev"}

#: full-game gameplay starts here (New Game -> rGuy1 in scripts/new_game +
#: room flow; menu rooms carry no player)
FULL_GAME_START = "rGuy1"

#: static-import classes (everything else is excluded + reported)
SOLID_OBJECTS = ("block", "blockNotMerge", "blockMini")
SPIKE_OBJECTS = {"spikeUp": ("^", "spike_up"), "spikeDown": ("v", "spike_down"),
                 "spikeLeft": ("<", "spike_left"),
                 "spikeRight": (">", "spike_right")}
KILLER_RECT_OBJECTS = ("blockKill",)
#: save object -> difficulty mask (bit d = exists on difficulty d), read
#: from the source Create events: saveMedium destroys if diff>0,
#: saveHard if diff>1, saveVeryHard/saveVeryEvil if diff>2
SAVE_OBJECTS = {"saveMedium": 0b0001, "saveHard": 0b0011,
                "saveVeryHard": 0b0111, "saveVeryEvil": 0b0111}
WARP_OBJECTS = ("warp",)
START_OBJECT = "playerStart"
#: player spawns at playerStart position + its origin offset
#: (scripts/room_start.gml: instance_create(x+17, y+23, player))
START_OFFSET = (17.0, 23.0)

_ASSIGN = re.compile(
    r"\b(roomTo|warpX|warpY|warpXhoff|warpYvoff|image_xscale|image_yscale)"
    r"\s*=\s*([A-Za-z_]\w*|-?\d+(?:\.\d+)?)(?:\s*/\s*(\d+(?:\.\d+)?))?")
_COND = re.compile(r"if\s*\(\s*savedata\(\"(\w+)\"\)\s*\)\s*\{(.*?)\}", re.S)
_CODE_STR = re.compile(r"\bcode\s*=\s*\"([^\"]*)\"", re.S)
_ROOM_GOTO = re.compile(r"room_goto(?:_fixed)?\s*\(\s*([A-Za-z_]\w*)")


class ConversionError(Exception):
    pass


def _num(v: str, room: dict[str, float]) -> float:
    if re.fullmatch(r"-?\d+(?:\.\d+)?", v):
        return float(v)
    if v in room:
        return room[v]
    raise KeyError(v)


def _parse_assigns(code: str, roomvars: dict[str, float]) -> tuple[dict, list]:
    """Parse the recognized assignment statements; return (values, residual
    statement list). Room identifiers (roomTo=rX) stay strings."""
    out: dict[str, Any] = {}
    for key, val, div in _ASSIGN.findall(code):
        if re.fullmatch(r"-?\d+(?:\.\d+)?", val):
            x = float(val)
        elif val in roomvars:
            x = roomvars[val]
        else:
            out[key] = val          # identifier (a room name)
            continue
        if div:
            x /= float(div)
        out[key] = x
    residual = []
    stripped = _COND.sub("", _CODE_STR.sub("", code))
    for stmt in re.split(r"[\n;]", stripped):
        s = stmt.strip()
        if not s or s.startswith("//") or s.startswith("/*"):
            continue
        if _ASSIGN.match(s) or re.match(
                r"^(depth|visible|nobug|dest|bowsercrash|crashy|image_speed)"
                r"\s*=", s):
            continue
        if s in ("{", "}"):
            continue
        residual.append(s)
    return out, residual


def _sprite_geom(proj, obj_name: str):
    o = proj.objects[obj_name]
    spr = proj.sprites.get(o.mask or o.sprite)
    p = spr.props if spr else {}
    return (float(p.get("origin_x", 0)), float(p.get("origin_y", 0)),
            float(p.get("bbox_left", 0)), float(p.get("bbox_top", 0)),
            float(p.get("bbox_right", 31)), float(p.get("bbox_bottom", 31)))


def _world_bbox(proj, obj: str, x: float, y: float, xs: float, ys: float):
    """GM-style world bbox (inclusive ints) of an unrotated scaled instance."""
    ox, oy, bl, bt, br, bb = _sprite_geom(proj, obj)
    x0 = x + (bl - ox) * xs
    y0 = y + (bt - oy) * ys
    x1 = x + (br + 1 - ox) * xs - 1
    y1 = y + (bb + 1 - oy) * ys - 1
    return x0, y0, x1, y1


def _warp_dest(vals: dict) -> dict:
    """Exact per-axis semantics of objects/warp.gml Collision_player."""
    wx = float(vals.get("warpX", 0) or 0)
    wy = float(vals.get("warpY", 0) or 0)
    hx = float(vals.get("warpXhoff", 0) or 0)
    vy = float(vals.get("warpYvoff", 0) or 0)
    if wx == 0 and wy == 0:
        return {"mode": "target_start"}
    x_abs = (hx == 0 and wx != 0)
    y_abs = (vy == 0 and wy != 0)
    if x_abs and y_abs:
        return {"mode": "absolute_keep", "dest_x": wx, "dest_y": wy}
    if x_abs:
        return {"mode": "x_abs_y_off", "dest_x": wx, "dest_y": vy}
    if y_abs:
        return {"mode": "x_off_y_abs", "dest_x": hx, "dest_y": wy}
    return {"mode": "offset", "dest_x": hx, "dest_y": vy}


def convert(source_root: str) -> dict[str, Any]:
    """Return {"ir": <gamepack IR>, "graph": <room graph>,
    "coverage": <static-import coverage report>}."""
    from tools.importers.iwbtgr.gm82 import load_project
    from tools.importers.iwbtgr.inventory import tree_sha256

    proj = load_project(source_root)
    room_names = proj.room_order
    room_index = {n: i for i, n in enumerate(room_names)}
    if FULL_GAME_START not in room_index:
        raise ConversionError(f"source has no {FULL_GAME_START} room")

    ir = new_gamepack(
        GAME_ID,
        title="I Wanna Be The Guy: Remastered 1.5.3 (static world)",
        source_game="I Wanna Be The Guy: Remastered",
        source_version="1.5.3",
        source_format="GameMaker 8.2 gm82save text tree",
        importer=f"games.iwbtgr_1_5_3.converter",
        importer_version=CONVERTER_VERSION,
    )
    ir["provenance"]["source_checksum_sha256"] = tree_sha256(source_root)
    ir["global_flags"] = [
        {"id": fid, "name": name,
         "provenance": {"source_game": "IWBTGR", "source_object": "savedata"}}
        for name, fid in sorted(PROGRESSION_FLAGS.items(), key=lambda kv: kv[1])]
    # No terminal goal in the static world: completion in the source is
    # boss-gated (The Guy), which is dynamic content. Episodes end by
    # death/timeout; success signals come later with boss import.
    ir["completion"] = {"type": "none",
                        "note": "completion is boss-gated (dynamic); "
                                "not part of the static-world import"}
    # object definitions only for the entity kinds actually emitted
    ir["object_definitions"] = []

    graph_edges: list[dict[str, Any]] = []
    graph_rooms: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {
        "imported_by_object": Counter(),
        "excluded_by_object": Counter(),
        "excluded_reasons": {},
        "residual_code": [],
        "side_effects": [],
        "conditional_unlowered": [],
        "geometry": Counter(),
    }
    scripted = defaultdict(set)   # room -> {(object, target)}
    for oname, o in proj.objects.items():
        targets = set()
        for e in o.events:
            targets.update(_ROOM_GOTO.findall(e.code))
        if targets:
            for rn, room in proj.rooms.items():
                if any(i.object == oname for i in room.instances):
                    for t in targets:
                        if t in room_index:
                            scripted[rn].add((oname, t))

    warp_tag = 40   # entity tags for conditional warp pairs (well clear of 0)

    for rname in room_names:
        src = proj.rooms[rname]
        roomvars = {"room_width": float(src.width),
                    "room_height": float(src.height)}
        tw = -(-src.width // TILE)
        th = -(-src.height // TILE)
        room = new_room(room_index[rname], rname, tw, th)
        room["px_size"] = [src.width, src.height]
        grid = [["."] * tw for _ in range(th)]
        solids: list[list[float]] = []
        killers: list[dict[str, Any]] = []
        imported = Counter()
        excluded = Counter()
        saves_by_diff = Counter()
        room_edges: list[dict[str, Any]] = []

        for inst in src.instances:
            obj = inst.object
            x, y, xs, ys = inst.x, inst.y, inst.xscale, inst.yscale
            cc_vals: dict[str, Any] = {}
            residual: list[str] = []
            if inst.creation_code:
                cc_vals, residual = _parse_assigns(inst.creation_code, roomvars)
                vx = cc_vals.get("image_xscale")
                vy = cc_vals.get("image_yscale")
                if isinstance(vx, float):
                    xs *= vx
                if isinstance(vy, float):
                    ys *= vy

            if obj in SOLID_OBJECTS:
                x0, y0, x1, y1 = _world_bbox(proj, obj, x, y, xs, ys)
                if (x0 % TILE == 0 and y0 % TILE == 0 and
                        (x1 + 1) % TILE == 0 and (y1 + 1) % TILE == 0 and
                        0 <= x0 and 0 <= y0 and x1 < tw * TILE and y1 < th * TILE):
                    for tyy in range(int(y0) // TILE, int(y1 + 1) // TILE):
                        for txx in range(int(x0) // TILE, int(x1 + 1) // TILE):
                            grid[tyy][txx] = "#"
                    coverage["geometry"]["solid_tiles_rasterized"] += 1
                else:
                    solids.append([x0, y0, x1, y1])
                    coverage["geometry"]["solid_rects"] += 1
                imported[obj] += 1
            elif obj in SPIKE_OBJECTS:
                ch, shape = SPIKE_OBJECTS[obj]
                if (xs == 1 and ys == 1 and x % TILE == 0 and y % TILE == 0
                        and 0 <= x < tw * TILE and 0 <= y < th * TILE):
                    grid[int(y) // TILE][int(x) // TILE] = ch
                    coverage["geometry"]["spike_tiles_rasterized"] += 1
                else:
                    x0, y0, x1, y1 = _world_bbox(proj, obj, x, y, xs, ys)
                    killers.append({"shape": shape, "x0": x0, "y0": y0,
                                    "x1": x1, "y1": y1})
                    coverage["geometry"]["spike_killers"] += 1
                imported[obj] += 1
            elif obj in KILLER_RECT_OBJECTS:
                x0, y0, x1, y1 = _world_bbox(proj, obj, x, y, xs, ys)
                killers.append({"shape": "rect", "x0": x0, "y0": y0,
                                "x1": x1, "y1": y1})
                coverage["geometry"]["killer_rects"] += 1
                imported[obj] += 1
            elif obj in SAVE_OBJECTS:
                ox, oy, bl, bt, br, bb = _sprite_geom(proj, obj)
                room["checkpoints"].append({
                    "x": x + (bl + br + 1) / 2.0,
                    "y": y + (bt + bb + 1) / 2.0,
                    "half_w": (br - bl + 1) / 2.0,
                    "half_h": (bb - bt + 1) / 2.0,
                    "difficulty_mask": SAVE_OBJECTS[obj],
                    "source_object": obj,
                    "source_instance": inst.id_hex,
                })
                for d in range(4):
                    if (SAVE_OBJECTS[obj] >> d) & 1:
                        saves_by_diff[d] += 1
                imported[obj] += 1
            elif obj in WARP_OBJECTS:
                hw, hh = 16.0 * xs, 16.0 * ys
                cx, cy = x + hw, y + hh
                cond = None
                variant_vals = None
                base = {}
                if inst.creation_code:
                    # base = statements OUTSIDE any conditional block;
                    # the variant inherits the base then applies the block
                    # (source execution order)
                    base, _ = _parse_assigns(_COND.sub("", inst.creation_code),
                                             roomvars)
                    m = _COND.search(inst.creation_code)
                    if m:
                        cond = m.group(1)
                        vv, _ = _parse_assigns(m.group(2), roomvars)
                        variant_vals = {**base, **vv}
                    for c in _CODE_STR.findall(inst.creation_code):
                        coverage["side_effects"].append(
                            {"room": rname, "at": [x, y], "code": c,
                             "status": "recorded_not_implemented"})
                dest = _warp_dest(base)
                room_to = base.get("roomTo")
                wp = {"x": cx, "y": cy, "half_w": hw, "half_h": hh,
                      "mode": dest["mode"],
                      "dest_x": dest.get("dest_x"), "dest_y": dest.get("dest_y"),
                      "dest_room": room_index.get(room_to) if
                      isinstance(room_to, str) else None,
                      "source_instance": inst.id_hex}
                edge = {"from": rname,
                        "to": room_to if isinstance(room_to, str) else rname,
                        "via": "warp", "x": x, "y": y,
                        "half_w": hw, "half_h": hh,
                        "mode": dest["mode"], "dest": dest,
                        "condition": None, "lowered": True,
                        "source_instance": inst.id_hex}
                if cond is not None and variant_vals is not None:
                    # conditional warp: base active, variant dormant,
                    # switched by the progression flag (exact lowering of
                    # `if (savedata("K")) {...}`)
                    flag = PROGRESSION_FLAGS.get(cond)
                    vdest = _warp_dest(variant_vals)
                    v_room = variant_vals.get("roomTo")
                    v_room_idx = room_index.get(v_room) if \
                        isinstance(v_room, str) else None
                    if flag is not None:
                        base_tag, var_tag = warp_tag, warp_tag + 1
                        warp_tag += 2
                        wp["tag"] = base_tag
                        vp = {"x": cx, "y": cy, "half_w": hw, "half_h": hh,
                              "mode": vdest["mode"],
                              "dest_x": vdest.get("dest_x"),
                              "dest_y": vdest.get("dest_y"),
                              "dest_room": v_room_idx,
                              "tag": var_tag, "active": False,
                              "source_instance": inst.id_hex}
                        room["warps"].append(vp)
                        room["events"].append({
                            "when": "flag_set", "flag": flag, "once": True,
                            "actions": [{"do": "deactivate", "tag": base_tag},
                                        {"do": "activate", "tag": var_tag}],
                            "mapping_status": "exact",
                            "provenance": {"source_room": rname,
                                           "source_instance": inst.id_hex,
                                           "source_event":
                                               f'savedata("{cond}") warp'},
                        })
                        v_edge = dict(edge, dest=vdest,
                                      to=v_room if isinstance(v_room, str)
                                      else rname,
                                      condition={"savedata": cond},
                                      mode=vdest["mode"])
                        room_edges.append(v_edge)
                    else:
                        coverage["conditional_unlowered"].append(
                            {"room": rname, "at": [x, y],
                             "condition": cond,
                             "reason": "condition key has no flag mapping"})
                room["warps"].append(wp)
                room_edges.append(edge)
                imported[obj] += 1
            elif obj == START_OBJECT:
                room["start"] = {"x": x + START_OFFSET[0],
                                 "y": y + START_OFFSET[1]}
                imported[obj] += 1
            elif obj == "EntranceTele":
                # final-area gate: parent=warp, config in its Create event
                # (roomTo=rGuyRoad, image_xscale=370/16); its Collision_player
                # requires all six boss orbs — an AND condition the event
                # system cannot express yet, so the transition is NOT lowered
                # (recorded conditional edge; use set_gflag/room mode to
                # inspect the gated area)
                ev = proj.objects[obj].event("Create_0")
                vals, _res = _parse_assigns(ev.code if ev else "", roomvars)
                exs = float(vals.get("image_xscale", 1.0))
                eys = float(vals.get("image_yscale", 1.0))
                x0, y0, x1, y1 = _world_bbox(proj, obj, x, y, exs, eys)
                edge = {"from": rname, "to": str(vals.get("roomTo")),
                        "via": "EntranceTele",
                        "x": x, "y": y,
                        "half_w": (x1 - x0 + 1) / 2, "half_h": (y1 - y0 + 1) / 2,
                        "mode": "target_start",
                        "dest": {"mode": "target_start"},
                        "condition": {"all_of": sorted(
                            k for k in PROGRESSION_FLAGS if k != "orb_dragon"
                            and k != "orb_guy")},
                        "lowered": False,
                        "source_instance": inst.id_hex}
                room_edges.append(edge)
                coverage["conditional_unlowered"].append(
                    {"room": rname, "at": [x, y],
                     "condition": "all of 6 boss orbs (EntranceTele)",
                     "reason": "AND-condition lowering not supported yet"})
                excluded[obj] += 1
                coverage["excluded_reasons"][obj] = \
                    "conditional final-gate transition (graph edge recorded)"
            else:
                excluded[obj] += 1
                if obj not in coverage["excluded_reasons"]:
                    coverage["excluded_reasons"][obj] = "dynamic/visual/meta " \
                        "object — not part of the static world import"
            if residual:
                coverage["residual_code"].append(
                    {"room": rname, "object": obj, "at": [inst.x, inst.y],
                     "statements": residual})

        room["tiles"] = ["".join(r) for r in grid]
        room["solids"] = solids
        room["killers"] = killers
        ir["rooms"].append(room)
        coverage["imported_by_object"].update(imported)
        coverage["excluded_by_object"].update(excluded)
        graph_edges.extend(room_edges)
        graph_rooms.append({
            "id": room_index[rname], "name": rname,
            "px": [src.width, src.height], "tiles": [tw, th],
            "meta_room": rname in META_ROOMS,
            "start": [room["start"]["x"], room["start"]["y"]]
            if room.get("start") else None,
            "saves_by_difficulty": {
                "medium": saves_by_diff.get(0, 0),
                "hard": saves_by_diff.get(1, 0),
                "very_hard": saves_by_diff.get(2, 0),
                "impossible": saves_by_diff.get(3, 0)},
            "imported_instances": sum(imported.values()),
            "excluded_instances": sum(excluded.values()),
            "scripted_transitions": sorted(
                {f"{o}->{t}" for o, t in scripted.get(rname, ())}),
        })

    ir["room_graph"]["start_room"] = room_index[FULL_GAME_START]
    ir["room_graph"]["edges"] = [
        [room_index[e["from"]], room_index.get(e["to"], -1), e["via"]]
        for e in graph_edges if e.get("lowered")]

    # ---- reachability over the graph (warp edges + gated edges) ----
    adj_now = defaultdict(set)
    adj_all = defaultdict(set)
    for e in graph_edges:
        if e["to"] in room_index:
            adj_all[e["from"]].add(e["to"])
            if e["condition"] is None:
                adj_now[e["from"]].add(e["to"])
    for rn in scripted:
        for _o, t in scripted[rn]:
            adj_all[rn].add(t)

    def reach(adj, start):
        seen, stack = set(), [start]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adj.get(n, ()))
        return seen

    reachable_now = sorted(reach(adj_now, FULL_GAME_START))
    reachable_all = sorted(reach(adj_all, FULL_GAME_START))
    orphans = [r for r in room_names
               if r not in reachable_all and r not in META_ROOMS]

    graph = {
        "game": GAME_ID,
        "source_tree_sha256": ir["provenance"]["source_checksum_sha256"],
        "converter_version": CONVERTER_VERSION,
        "start_room_full_game": FULL_GAME_START,
        "room_order": room_names,
        "rooms": graph_rooms,
        "edges": graph_edges,
        "progression_flags": PROGRESSION_FLAGS,
        "reachable_without_flags": reachable_now,
        "reachable_with_all_flags_and_scripts": reachable_all,
        "orphaned_required_rooms": orphans,
        "notes": [
            "edges parsed mechanically from warp creation code "
            "(objects/warp.gml per-axis semantics) and EntranceTele's "
            "Create/Collision events",
            "scripted_transitions list room_goto targets of dynamic objects "
            "placed in each room (bosses, endings) — not lowered yet",
            "player spawn = playerStart + (17,23) per scripts/room_start.gml",
        ],
    }
    coverage["imported_by_object"] = dict(coverage["imported_by_object"])
    coverage["excluded_by_object"] = dict(
        coverage["excluded_by_object"].most_common())
    coverage["geometry"] = dict(coverage["geometry"])
    coverage["totals"] = {
        "instances_in_source": sum(len(r.instances)
                                   for r in proj.rooms.values()),
        "instances_imported": sum(coverage["imported_by_object"].values()),
        "instances_excluded": sum(coverage["excluded_by_object"].values()),
    }
    return {"ir": ir, "graph": graph, "coverage": coverage}
