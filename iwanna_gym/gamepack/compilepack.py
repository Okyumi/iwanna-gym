"""Compiler: canonical IR (.iwgame.json) -> compact binary pack (.iwpack).

The output layout mirrors c_src/gamepack/iwpack.h exactly (little-endian,
fixed-width records, precomputed offsets, per-pack maxima). The runtime
decodes it once at construction; nothing here ever runs during stepping.

Unsupported/unknown elements are a hard compile error unless
``allow_unsupported=True``; then they are DROPPED VISIBLY: listed in the
pack metadata under ``dropped`` with ``incomplete: true``, and echoed in
the returned CompileResult. Silent discarding is a bug by definition.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from typing import Any

from .schema import (
    ACTION_PROFILES,
    CM_PLAYER,
    EF_ACTIVE,
    EF_DEADLY,
    EF_DORMANT,
    EF_SOLID_TOP,
    ENTITY_KINDS,
    EVENT_ACTIONS,
    EVENT_WHEN,
    PHYSICS_PROFILES,
    TILE_CHARS,
    TILE_PX,
)
from .validate import validate

PACK_MAGIC = 0x4B505749  # "IWPK"
PACK_VERSION = 2

_HDR = struct.Struct("<20I")
_ROOM = struct.Struct("<IIIIffffI4i11I")
_ENT = struct.Struct("<IIiiI fffff ii 6f".replace(" ", ""))
_EVT = struct.Struct("<IIIiii ffff iiii".replace(" ", ""))
_ACT = struct.Struct("<Ii6f")
_SOLID = struct.Struct("<4f")
_KILLER = struct.Struct("<I4f")

KILLER_SHAPES = {"rect": 0, "spike_up": 1, "spike_down": 2,
                 "spike_left": 3, "spike_right": 4}

#: warp destination modes (mirror iwanna.h E_WARP params[5])
WARP_MODES = {"absolute": 0, "offset": 1, "target_start": 2,
              "absolute_keep": 3, "x_abs_y_off": 4, "x_off_y_abs": 5}

# player hitbox constants (mirror iwanna.h) used for start placement
_HB_B = 8
_DIRS = {"up": 0, "down": 1, "left": 2, "right": 3}


class CompileError(Exception):
    pass


@dataclass
class CompileResult:
    data: bytes
    dropped: list[str] = field(default_factory=list)
    n_rooms: int = 0
    size: int = 0


def _f(v: Any, default: float = 0.0) -> float:
    return float(v) if v is not None else default


def _lower_entity(kind: str, inst: dict, room_of: dict[str, int]) -> tuple:
    """Return the IWPackEnt tuple for one instance (px coordinates)."""
    p = dict(inst.get("params") or {})
    x, y = float(inst["x"]), float(inst["y"])
    tag = int(inst.get("tag") or p.get("tag") or 0)
    etype = ENTITY_KINDS[kind]
    flags = EF_ACTIVE
    trigger_id = int(p.get("id") or 0)
    state = 0
    timer = 0
    params = [0.0] * 6
    vx, vy = _f(p.get("vx")), _f(p.get("vy"))
    grav = _f(p.get("grav"))

    if kind == "platform":
        flags |= EF_SOLID_TOP
        params[0] = _f(p.get("range"))
        params[4], params[5] = x, y
    elif kind in ("spikeball", "enemy"):
        flags |= EF_DEADLY
        params[0] = _f(p.get("range"))
        params[4], params[5] = x, y
    elif kind == "trap":
        flags |= EF_DEADLY | EF_DORMANT
        params[2], params[3] = vx, vy      # launch velocity on trigger
        vx = vy = 0.0
        params[4] = float(_DIRS.get(p.get("dir", "up"), 0))
    elif kind == "trigger_zone":
        params[0] = _f(p.get("half_w"), TILE_PX / 2)
        params[1] = _f(p.get("half_h"), TILE_PX / 2)
    elif kind == "shooter":
        period = _f(p.get("period"), 60)
        speed = _f(p.get("speed"), 4)
        params[0] = period
        params[1] = speed
        params[2] = 1.0 if p.get("aimed") else 0.0
        d = p.get("dir", "up")
        dvx = -speed if d == "left" else speed if d == "right" else 0.0
        dvy = -speed if d == "up" else speed if d == "down" else 0.0
        params[3], params[4] = dvx, dvy
        timer = int(period)
    elif kind == "save":
        params[0] = float(int(p.get("difficulty_mask", 0)))
        params[3] = _f(p.get("half_w"))
        params[4] = _f(p.get("half_h"))
    elif kind == "warp":
        params[0] = _f(p.get("dest_x"), x)
        params[1] = _f(p.get("dest_y"), y)
        dr = p.get("dest_room")
        if isinstance(dr, str):
            dr = room_of[dr]
        params[2] = 0.0 if dr is None else float(int(dr) + 1)
        params[3] = _f(p.get("half_w"))
        params[4] = _f(p.get("half_h"))
        params[5] = float(WARP_MODES.get(p.get("mode", "absolute"), 0))
    elif kind == "boss_radial8":
        flags |= EF_DEADLY
        period = _f(p.get("period"), 100)
        volleys = _f(p.get("volleys"), 0)
        params[0], params[1] = period, volleys
        state = int(volleys)
        timer = int(period)
    elif kind == "gate":
        tx = int(p.get("tx", int(x) // TILE_PX))
        ty = int(p.get("ty", int(y) // TILE_PX))
        w = int(p.get("w", 1))
        h = int(p.get("h", 1))
        params[0], params[1] = float(tx), float(ty)
        params[2], params[3] = float(w), float(h)
        params[4] = float(w * 100 + h)
        x = (tx + w / 2.0) * TILE_PX
        y = (ty + h / 2.0) * TILE_PX
        state = 0 if p.get("open") else 1
    elif kind == "projectile":
        flags |= EF_DEADLY
    else:  # pragma: no cover — validated upstream
        raise CompileError(f"unhandled entity kind {kind!r}")

    if inst.get("active") is False or p.get("active") in (0, False):
        flags &= ~EF_ACTIVE
    return (etype, flags, trigger_id, tag, CM_PLAYER,
            x, y, vx, vy, grav, state, timer, *params)


def _lower_action(a: dict) -> tuple:
    do = a["do"]
    t = EVENT_ACTIONS[do]
    tag = -1
    p = [0.0] * 6
    if do in ("set_flag", "clear_flag", "start_timer"):
        tag = int(a.get("id", a.get("flag", 0)))
    elif do == "spawn":
        spawn_types = {"platform": 1, "spikeball": 2, "trap": 4,
                       "projectile": 5, "enemy": 7}
        p[0] = float(spawn_types.get(a.get("kind", "projectile"), 5))
        p[1], p[2] = _f(a.get("x")), _f(a.get("y"))
        p[3], p[4] = _f(a.get("vx")), _f(a.get("vy"))
        p[5] = _f(a.get("grav"))
        tag = 1 if a.get("deadly", True) else -1
    elif do == "teleport" and "tag" not in a:
        tag = -1                       # player teleport
        p[0], p[1] = _f(a.get("x")), _f(a.get("y"))
    else:
        tag = int(a.get("tag", -1))
        if do == "launch":
            p[0], p[1] = _f(a.get("vx")), _f(a.get("vy"))
            p[2] = _f(a.get("grav"))
        elif do == "set_gravity":
            p[0] = _f(a.get("grav"))
        elif do == "move":
            p[0], p[1] = _f(a.get("dx")), _f(a.get("dy"))
        elif do == "teleport":
            p[0], p[1] = _f(a.get("x")), _f(a.get("y"))
        elif do == "set_dir":
            p[0] = float(_DIRS.get(a.get("dir", "up"), 0))
    return (t, tag, *p)


def _lower_event(ev: dict, first_action: int, n_actions: int) -> tuple:
    when = EVENT_WHEN[ev["when"]]
    once = 1 if ev.get("once", True) else 0
    if ev.get("period") and "once" not in ev:
        once = 0                       # periodic timers refire by default
    auto = 1 if ev.get("auto", True) else 0
    dirmap = {"any": 0, "right": 1, "down": 1, "left": -1, "up": -1}
    d = dirmap.get(ev.get("dir", "any"), 0)
    x0 = _f(ev.get("x0", ev.get("x")))
    y0 = _f(ev.get("y0", ev.get("y")))
    x1 = _f(ev.get("x1"))
    y1 = _f(ev.get("y1"))
    if "tag" in ev:
        subject = int(ev["tag"])
    elif "flag" in ev:
        subject = int(ev["flag"])
    else:
        subject = -1
    return (when, once, auto, d, int(ev.get("id", 0)), subject,
            x0, y0, x1, y1,
            int(ev.get("delay", 0)), int(ev.get("period", 0)),
            first_action, n_actions)


_XHDR = struct.Struct("<14I4i4I")
_XMASK = struct.Struct("<8h2HI")
_XOP = struct.Struct("<2i3f")
_XENT = struct.Struct("<2H4fiIi10f")
_XROOM = struct.Struct("<8I")


def _pack_exact_section(x: dict, section_base: int) -> bytes:
    """Serialize the exact-behavior section (see c_src/exact.h)."""
    body = bytearray()

    def pad4():
        while len(body) % 4:
            body.append(0)

    # mask bitmap pool
    bits: list[int] = []
    mask_recs = []
    for m in x["masks"]:
        w, h = int(m["w"]), int(m["h"])
        words_per_row = (w + 31) // 32
        word0 = len(bits)
        frames = m.get("rows") or []
        for fr in frames:
            for row_hex in fr:
                row = int(row_hex, 16) if row_hex else 0
                for j in range(words_per_row):
                    bits.append((row >> (32 * j)) & 0xFFFFFFFF)
        nfr = max(1, len(frames))
        mask_recs.append((w, h, int(m["ox"]), int(m["oy"]),
                          int(m["bl"]), int(m["bt"]), int(m["br"]),
                          int(m["bb"]), int(m["shape"]), nfr, word0))

    off_hdr = len(body)
    body += b"\0" * _XHDR.size

    masks_off = section_base + len(body)
    for r in mask_recs:
        body += _XMASK.pack(*r)
    bits_off = section_base + len(body)
    for wdd in bits:
        body += struct.pack("<I", wdd)
    ops_off = section_base + len(body)
    for op in x["ops"]:
        body += _XOP.pack(int(op[0]), int(op[1]),
                          float(op[2]), float(op[3]), float(op[4]))
    tmpl_off = section_base + len(body)
    for t in x["templates"]:
        body += _XENT.pack(int(t["cls"]), int(t["mask"]), 0.0, 0.0,
                           float(t["xs"]), float(t["ys"]), -1,
                           int(t["flags"]), -1,
                           *[float(v) for v in t["p"]])
    keys_off = section_base + len(body)
    for k in x["keys"]:
        body += struct.pack("<f", float(k))
    xrooms_off = section_base + len(body)
    ent_blocks = []
    max_xents = 0
    for rm in x["rooms"]:
        max_xents = max(max_xents, len(rm["xents"]))
    # per-room entity arrays FOLLOW the room table; record placeholders
    room_tbl_off = len(body)
    body += b"\0" * (_XROOM.size * len(x["rooms"]))
    for rm in x["rooms"]:
        pad4()
        e_off = section_base + len(body)
        for e in rm["xents"]:
            body += _XENT.pack(int(e["cls"]), int(e["mask"]),
                               float(e["x"]), float(e["y"]),
                               float(e["xs"]), float(e["ys"]),
                               int(e["tag"]), int(e["flags"]),
                               int(e.get("link", -1)),
                               *[float(v) for v in e["p"]])
        ent_blocks.append((len(rm["xents"]), e_off))
    for i, rm in enumerate(x["rooms"]):
        n, off = ent_blocks[i]
        eo = rm.get("enter_ops", [0, 0])
        struct.pack_into(_XROOM.format, body,
                         room_tbl_off + i * _XROOM.size,
                         n, off, int(rm["camera"]),
                         int(rm["always_active"]),
                         int(eo[0]), int(eo[1]),
                         int(rm.get("kind", 0)), 0)
    hb = x.get("hb", [-5, -12, 5, 8])
    struct.pack_into(_XHDR.format, body, off_hdr,
                     0x33544358,
                     len(mask_recs), masks_off,
                     bits_off, len(bits),
                     len(x["ops"]), ops_off,
                     len(x["templates"]), tmpl_off,
                     len(x["keys"]), keys_off,
                     len(x["rooms"]), xrooms_off,
                     max_xents,
                     int(hb[0]), int(hb[1]), int(hb[2]), int(hb[3]),
                     int(x.get("flags", 1)), 0, 0, 0)
    return bytes(body)


def compile_pack(doc: dict[str, Any], allow_unsupported: bool = False) -> CompileResult:
    rep = validate(doc, allow_unsupported=allow_unsupported)
    if not rep.ok:
        raise CompileError("IR failed validation:\n" + rep.text())
    dropped = list(rep.unsupported) if allow_unsupported else []
    dropped_set = set(dropped)

    objdefs = {od["name"]: od for od in doc.get("object_definitions", [])}
    rooms = doc["rooms"]
    room_of = {r["name"]: r["id"] for r in rooms}

    # ---- lower each room ----
    lowered = []
    for room in rooms:
        rn = room.get("name", str(room["id"]))
        w, h = room["width_tiles"], room["height_tiles"]
        tiles = bytearray(w * h)
        start = None
        goal = None
        for y, row in enumerate(room["tiles"]):
            for x, ch in enumerate(row):
                tiles[y * w + x] = TILE_CHARS[ch]
                if ch == "S":
                    start = (x * TILE_PX + TILE_PX / 2.0,
                             y * TILE_PX + (TILE_PX - 1) - _HB_B)
                elif ch == "G":
                    goal = (x * TILE_PX + TILE_PX / 2.0,
                            y * TILE_PX + TILE_PX / 2.0)
        if room.get("start"):
            start = (float(room["start"]["x"]), float(room["start"]["y"]))
        if room.get("goal"):
            goal = (float(room["goal"]["x"]), float(room["goal"]["y"]))

        ents: list[tuple] = []
        for i, inst in enumerate(room.get("instances", [])):
            where = f"rooms/{rn}/instances[{i}]({inst.get('object')})"
            if where in dropped_set:
                continue
            od = objdefs[inst["object"]]
            if od.get("mapping_status") in ("unsupported", "unknown"):
                if f"object_definitions/{od['name']}" in dropped_set:
                    dropped.append(where)
                    continue
            kind = od["kind"]
            if kind == "player_start":
                start = (float(inst["x"]), float(inst["y"]))
                continue
            if kind.startswith("tile_"):
                code = {"tile_block": 1, "tile_spike_up": 2,
                        "tile_spike_down": 3, "tile_spike_left": 4,
                        "tile_spike_right": 5, "tile_goal": 6}[kind]
                tx, ty = int(inst["x"]) // TILE_PX, int(inst["y"]) // TILE_PX
                if 0 <= tx < w and 0 <= ty < h:
                    tiles[ty * w + tx] = code
                    if kind == "tile_goal":
                        goal = (tx * TILE_PX + TILE_PX / 2.0,
                                ty * TILE_PX + TILE_PX / 2.0)
                else:
                    raise CompileError(f"{where}: tile instance outside room")
                continue
            ents.append(_lower_entity(kind, inst, room_of))

        for cp in room.get("checkpoints", []):
            ents.append(_lower_entity("save", {
                "x": cp["x"], "y": cp["y"], "tag": cp.get("tag", 0),
                "params": {"difficulty_mask": cp.get("difficulty_mask", 0),
                           "half_w": cp.get("half_w"),
                           "half_h": cp.get("half_h")},
            }, room_of))
        for wp in room.get("warps", []):
            went = _lower_entity("warp", {
                "x": wp["x"], "y": wp["y"], "tag": wp.get("tag", 0),
                "active": wp.get("active", True),
                "params": {"dest_x": wp.get("dest_x"),
                           "dest_y": wp.get("dest_y"),
                           "dest_room": wp.get("dest_room"),
                           "half_w": wp.get("half_w"),
                           "half_h": wp.get("half_h"),
                           "mode": wp.get("mode", "absolute")},
            }, room_of)
            if wp.get("xnops"):
                # exact-layer side-effect ops ride in trigger_id/state
                went = (went[0], went[1], int(wp["xop0"]), went[3], went[4],
                        went[5], went[6], went[7], went[8], went[9],
                        int(wp["xnops"]), went[11], *went[12:])
            ents.append(went)

        solids = [tuple(float(v) for v in s) for s in room.get("solids", [])]
        killers = [(KILLER_SHAPES[k["shape"]], float(k["x0"]), float(k["y0"]),
                    float(k["x1"]), float(k["y1"]))
                   for k in room.get("killers", [])]
        px = room.get("px_size") or [w * TILE_PX, h * TILE_PX]

        evts: list[tuple] = []
        acts: list[tuple] = []
        for i, ev in enumerate(room.get("events", [])):
            where = f"rooms/{rn}/events[{i}]({ev.get('when')})"
            if where in dropped_set:
                continue
            first = len(acts)
            for a in ev.get("actions", []):
                acts.append(_lower_action(a))
            evts.append(_lower_event(ev, first, len(acts) - first))

        edges = room.get("edges", {})
        edge = [edges.get(k) if edges.get(k) is not None else -1
                for k in ("left", "right", "up", "down")]
        edge = [room_of[e] if isinstance(e, str) else int(e) for e in edge]

        if start is None:
            start = (TILE_PX * 1.5, TILE_PX * 1.5)
        has_goal = 1 if goal is not None else 0
        if goal is None:
            # shaping objective only: first warp, else linked-edge midpoint,
            # else room center. has_goal=0 => never terminates the episode.
            warp_e = next((e for e in ents if e[0] == ENTITY_KINDS["warp"]), None)
            if warp_e is not None:
                goal = (warp_e[5], warp_e[6])
            elif edge[1] >= 0:
                goal = (w * TILE_PX - TILE_PX / 2.0, start[1])
            elif edge[0] >= 0:
                goal = (TILE_PX / 2.0, start[1])
            else:
                goal = (w * TILE_PX / 2.0, h * TILE_PX / 2.0)

        lowered.append(dict(w=w, h=h, px=(int(px[0]), int(px[1])),
                            tiles=bytes(tiles), start=start,
                            goal=goal, has_goal=has_goal, edge=edge,
                            ents=ents, evts=evts, acts=acts,
                            solids=solids, killers=killers))

    # ---- metadata blob: provenance survives into the pack ----
    elements = []
    from .schema import iter_elements
    for where, el in iter_elements(doc):
        elements.append({
            "where": where,
            "mapping_status": el.get("mapping_status"),
            "provenance": el.get("provenance", {}),
        })
    meta = {
        "metadata": doc.get("metadata", {}),
        "provenance": doc.get("provenance", {}),
        "global_flags": doc.get("global_flags", []),
        "physics_profile": doc.get("physics_profile"),
        "action_profile": doc.get("action_profile"),
        "rooms": [{"id": r["id"], "name": r.get("name", "")} for r in rooms],
        "completion": doc.get("completion", {}),
        "elements": elements,
        "dropped": sorted(set(dropped)),
        "incomplete": bool(dropped),
    }
    meta_bytes = json.dumps(meta, sort_keys=True).encode("utf-8")

    # ---- serialize ----
    def pad4(n: int) -> int:
        return (n + 3) & ~3

    body = bytearray()
    room_recs = []
    base = _HDR.size
    for lr in lowered:
        tiles_off = base + len(body)
        body += lr["tiles"]
        body += b"\0" * (pad4(len(body)) - len(body))
        spawns_off = base + len(body)
        for e in lr["ents"]:
            body += _ENT.pack(*e)
        events_off = base + len(body)
        for e in lr["evts"]:
            body += _EVT.pack(*e)
        actions_off = base + len(body)
        for a in lr["acts"]:
            body += _ACT.pack(*a)
        solids_off = base + len(body)
        for s in lr["solids"]:
            body += _SOLID.pack(*s)
        killers_off = base + len(body)
        for k in lr["killers"]:
            body += _KILLER.pack(*k)
        room_recs.append((lr, tiles_off, spawns_off, events_off, actions_off,
                          solids_off, killers_off))

    rooms_off = base + len(body)
    for lr, t_off, s_off, e_off, a_off, so_off, k_off in room_recs:
        body += _ROOM.pack(
            lr["w"], lr["h"], lr["px"][0], lr["px"][1],
            lr["start"][0], lr["start"][1],
            lr["goal"][0], lr["goal"][1],
            lr["has_goal"],
            *lr["edge"],
            t_off,
            len(lr["ents"]), s_off,
            len(lr["evts"]), e_off,
            len(lr["acts"]), a_off,
            len(lr["solids"]), so_off,
            len(lr["killers"]), k_off,
        )
    meta_off = base + len(body)
    body += meta_bytes

    x_off = x_len = 0
    version = PACK_VERSION
    if doc.get("exact"):
        body += b"\0" * (pad4(len(body)) - len(body))
        x_off = base + len(body)
        body += _pack_exact_section(doc["exact"], base + len(body))
        x_len = base + len(body) - x_off
        version = 3

    n_flags = max([f["id"] for f in doc.get("global_flags", [])], default=0) + 1
    n_flags = max(n_flags, 27)   # secret flags use bits 20..25
    hdr = _HDR.pack(
        PACK_MAGIC, version, _HDR.size + len(body),
        len(lowered), int(doc["room_graph"]["start_room"]), n_flags,
        PHYSICS_PROFILES[doc["physics_profile"]],
        ACTION_PROFILES[doc["action_profile"]],
        max(lr["w"] * lr["h"] for lr in lowered),
        max((len(lr["ents"]) for lr in lowered), default=0),
        max((len(lr["evts"]) for lr in lowered), default=0),
        max((len(lr["acts"]) for lr in lowered), default=0),
        max((len(lr["solids"]) for lr in lowered), default=0),
        max((len(lr["killers"]) for lr in lowered), default=0),
        rooms_off, meta_off, len(meta_bytes), x_off, x_len, 0,
    )
    data = bytes(hdr) + bytes(body)
    return CompileResult(data=data, dropped=sorted(set(dropped)),
                         n_rooms=len(lowered), size=len(data))
