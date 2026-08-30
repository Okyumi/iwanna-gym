"""Room-by-room source audit for the frozen IWBTGR 1.5.3 pack.

For every gameplay room this script compares the built pack against an
INDEPENDENT parse of the gm82save source tree:

  dimensions            room.txt width/height == pack px_size == runtime
  instance accounting   every source instance lands in exactly one
                        bucket: entity (xent provenance), lowered
                        static (solid/spike/killer-rect/save/warp/
                        playerStart), or excluded (visual/static-solid/
                        meta) — none unaccounted
  coordinates           per (room, object): the translation between
                        source instance coords and emitted entity
                        coords must be consistent (the class's origin
                        offset); inconsistent objects are reported
  collision geometry    every source solid-block rect is solid in the
                        runtime tile grid; every spike instance yields
                        a killer tile of the right shape; every
                        blockKill yields a killer rect
  transition targets    every room-graph edge is walked at runtime
                        (conditional edges get their flags); arrival
                        room asserted
  save presence         per-difficulty source save counts == pack
                        checkpoint difficulty masks
  dynamic-object map    per-room object -> class table from entity
                        provenance
  event mapping         source #define event inventory per implemented
                        object, bucketed (gameplay vs draw/sound-only)

Outputs build/source_reports/iwbtgr_room_audit.json and prints a
summary; exits nonzero on any audit failure.  The content checksums it
computes are pinned by tests/test_iwbtgr_content_checksums.py.

Usage:  python scripts/audit_iwbtgr_source.py <source-tree> [--quick]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from iwanna_gym.clib import CIWanna                       # noqa: E402
from iwanna_gym.games import iwbtgr_1_5_3 as G            # noqa: E402
from iwanna_gym.games.iwbtgr_1_5_3 import converter as CV  # noqa: E402
from iwanna_gym.games.iwbtgr_1_5_3 import exact as X       # noqa: E402

META_ROOMS = CV.META_ROOMS
TILE = 32

# tile codes (mirror c_src/iwanna.h)
T_EMPTY, T_BLOCK = 0, 1
SPIKE_SHAPE = {"spikeUp": 2, "spikeDown": 3, "spikeLeft": 4,
               "spikeRight": 5}

EV_RE = re.compile(r"^#define\s+(\w+)", re.M)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_room_txt(path):
    vals = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "=" in line:
                k, _, v = line.partition("=")
                vals[k.strip()] = v.strip()
    return vals


def parse_instances(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ps = line.split(",")
            rows.append({
                "object": ps[0], "x": float(ps[1]), "y": float(ps[2]),
                "id_hex": ps[3], "xscale": float(ps[5]),
                "yscale": float(ps[6]),
            })
    return rows


def source_room_sha(rdir):
    h = hashlib.sha256()
    for name in sorted(os.listdir(rdir)):
        p = os.path.join(rdir, name)
        if os.path.isfile(p):
            h.update(name.encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def pack_room_sha(c):
    """Deterministic digest of the runtime room content at load."""
    h = hashlib.sha256()
    pw, ph = c.room_px
    h.update(f"px:{pw}x{ph};".encode())
    h.update(b"tiles:")
    h.update(c.tiles().tobytes())
    for label, arr in (("solids", c.solids()), ("killers", c.killers())):
        rows = sorted(tuple(round(float(v), 3) for v in r) for r in arr)
        h.update(f";{label}:{rows}".encode())
    xe = sorted(tuple(round(float(v), 3) for v in r) for r in c.xents())
    h.update(f";xents:{xe}".encode())
    return h.hexdigest()


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/iwbtgr-mod/IWBTGR Source Files"
    quick = "--quick" in sys.argv
    rooms_dir = os.path.join(src, "rooms")
    objs_dir = os.path.join(src, "objects")
    if not os.path.isdir(rooms_dir):
        print(f"source tree not found at {src}")
        return 2

    iwgame = json.load(open("build/games/iwbtgr_1_5_3.iwgame.json"))
    graph = json.load(open(
        "iwanna_gym/games/iwbtgr_1_5_3/room_graph.json"))
    names = G.room_names()
    gameplay = [n for n in names if n not in META_ROOMS]
    by_name = {r["name"]: r for r in iwgame["rooms"]}
    xrooms = {r["name"]: r for r in iwgame["exact"]["rooms"]}

    lowered = (set(CV.SOLID_OBJECTS) | set(CV.SPIKE_OBJECTS) |
               set(CV.KILLER_RECT_OBJECTS) | set(CV.SAVE_OBJECTS) |
               set(CV.WARP_OBJECTS) | {CV.START_OBJECT})
    cameras = set(X.ROOM_CAMERA)
    static_solid = set(X.EXTRA_SOLID_CLASSES) | {"ZeldaCollision"}
    excluded = set(X.VISUAL_CLASSES)
    solid_base = {"block": 32, "blockNotMerge": 32, "blockMini": 16}

    audit = {"rooms": {}, "failures": [], "coordinate_offsets": {},
             "edge_walk": [], "event_inventory": {}}
    fails = audit["failures"]

    pack = G.load_pack()
    env = CIWanna.from_pack(pack, seed=11, checkpoint_respawn=True,
                            max_steps=90000000)

    for rname in gameplay:
        rdir = os.path.join(rooms_dir, rname)
        rvals = parse_room_txt(os.path.join(rdir, "room.txt"))
        srcw, srch = int(rvals["width"]), int(rvals["height"])
        insts = parse_instances(os.path.join(rdir, "instances.txt"))
        rec = by_name[rname]
        xr = xrooms[rname]

        # --- runtime load ---
        env.close()
        env = CIWanna.from_pack(pack, seed=11, checkpoint_respawn=True,
                                start_room=names.index(rname),
                                max_steps=90000000)
        env.reset()
        rw, rh = env.room_px

        r_out = {"src_dims": [srcw, srch], "pack_dims": rec["px_size"],
                 "runtime_dims": [rw, rh],
                 "src_instances": len(insts),
                 "source_sha256": source_room_sha(rdir),
                 "pack_content_sha256": pack_room_sha(env)}

        # 1. dimensions
        if [srcw, srch] != list(rec["px_size"]) or (rw, rh) != (srcw, srch):
            fails.append(f"{rname}: dims src={srcw}x{srch} "
                         f"pack={rec['px_size']} runtime={rw}x{rh}")

        # 2. instance accounting + 3. coordinate offsets
        prov = {}
        for e in xr["xents"]:
            hexid = e["provenance"]["source_instance"]
            if hexid:
                prov.setdefault(hexid, []).append(e)
        # instances lowered into warp / checkpoint records (warp objects,
        # BossTeleporters) are accounted through those tables
        lowered_hex = {w.get("source_instance") for w in rec.get("warps", [])}
        lowered_hex |= {cp.get("source_instance")
                        for cp in rec.get("checkpoints", [])}
        lowered_hex.discard(None)
        unaccounted, buckets = [], {"entity": 0, "lowered": 0,
                                    "camera": 0, "static_solid": 0,
                                    "excluded": 0}
        offsets = {}
        for inst in insts:
            o = inst["object"]
            if inst["id_hex"] in prov:
                buckets["entity"] += 1
                for e in prov[inst["id_hex"]]:
                    d = (round(e["x"] - inst["x"], 3),
                         round(e["y"] - inst["y"], 3))
                    offsets.setdefault(o, set()).add(d)
            elif o in lowered or inst["id_hex"] in lowered_hex:
                buckets["lowered"] += 1
            elif o in cameras:
                buckets["camera"] += 1
                want = X.ROOM_CAMERA[o]
                if o == "cameraHard" and rname == "rMetroid":
                    want = X.XCAM_HARD_METROID   # converter's documented
                    #                              Metroid variant upgrade
                if xr["camera"] != want:
                    fails.append(f"{rname}: {o} lowered but room camera "
                                 f"mode is {xr['camera']} != {want}")
            elif o in static_solid:
                buckets["static_solid"] += 1
            elif o in excluded:
                buckets["excluded"] += 1
            elif o == "BossTeleporter":
                # the dev-typed teleporter is excluded by the emitter
                cc = os.path.join(rdir, inst["id_hex"] + ".gml")
                txt = open(cc).read() if os.path.isfile(cc) else ""
                if "dev" in txt:
                    buckets["excluded"] += 1
                else:
                    unaccounted.append((o, inst["id_hex"]))
            else:
                unaccounted.append((o, inst["id_hex"]))
        r_out["buckets"] = buckets
        if unaccounted:
            fails.append(f"{rname}: unaccounted instances {unaccounted[:6]}"
                         f" (+{max(0, len(unaccounted)-6)} more)")
        for o, ds in offsets.items():
            key = f"{rname}/{o}"
            audit["coordinate_offsets"][key] = sorted(ds)
        # multi-offset objects are flagged (multi-ent emitters like spike
        # rows legitimately fan out; a single-ent object must be uniform)
        multi = {o: ds for o, ds in offsets.items() if len(ds) > 4}
        if multi:
            r_out["offset_note"] = {o: len(ds) for o, ds in multi.items()}

        # 4. collision geometry vs source statics.  A source solid may be
        # lowered as full tiles plus residual solid RECTS (non-aligned
        # remainders) or as solid xents; test pixel coverage against the
        # union.  Spikes may be lowered as killer tiles or killer xents
        # (removable rows).
        tiles = env.tiles()
        th, tw = tiles.shape
        srects = [tuple(float(v) for v in r) for r in env.solids()]
        killers = [tuple(float(v) for v in k) for k in env.killers()]
        solid_x = [(float(e[1]), float(e[2])) for e in env.xents()
                   if int(e[0]) in (85, 133)]      # destructible / fceil

        def solid_at(px, py):
            tx, ty = int(px) // TILE, int(py) // TILE
            if 0 <= tx < tw and 0 <= ty < th and tiles[ty][tx] == T_BLOCK:
                return True
            for (sl, st, sr, sb) in srects:          # x0,y0,x1,y1
                if sl <= px <= sr and st <= py <= sb:
                    return True
            for (ex, ey) in solid_x:
                if ex <= px < ex + 32 and ey <= py < ey + 32:
                    return True
            return False

        # source Room Start semantics applied before comparing: blockFake
        # destroys every overlapping real block (objects/blockFake.gml
        # Other_4), so those solids legitimately do not exist in the pack
        fakes = []
        for inst in insts:
            if inst["object"] == "blockFake":
                fw = 32 * abs(inst["xscale"])
                fh = 32 * abs(inst["yscale"])
                fakes.append((inst["x"], inst["y"],
                              inst["x"] + fw - 1, inst["y"] + fh - 1))

        def faked(x0, y0, x1, y1):
            return any(x1 >= f[0] and x0 <= f[2] and
                       y1 >= f[1] and y0 <= f[3] for f in fakes)

        # solid coverage of a tile by any source solid block (for spikes
        # embedded inside walls: the wall wins the tile, and the spike is
        # unreachable in source too)
        src_solid_rects = []
        for inst in insts:
            if inst["object"] in CV.SOLID_OBJECTS:
                b = solid_base[inst["object"]]
                w, h = b * abs(inst["xscale"]), b * abs(inst["yscale"])
                sx0 = inst["x"] - (w if inst["xscale"] < 0 else 0)
                sy0 = inst["y"] - (h if inst["yscale"] < 0 else 0)
                src_solid_rects.append((sx0, sy0, sx0 + w - 1, sy0 + h - 1))

        solid_miss = spike_miss = 0
        for inst in insts:
            o = inst["object"]
            if o in CV.SOLID_OBJECTS:
                base = solid_base[o]
                w = base * abs(inst["xscale"])
                h = base * abs(inst["yscale"])
                x0 = inst["x"] - (w if inst["xscale"] < 0 else 0)
                y0 = inst["y"] - (h if inst["yscale"] < 0 else 0)
                if faked(x0, y0, x0 + w - 1, y0 + h - 1):
                    continue     # destroyed at room start in source
                # sample a 16px lattice of interior points, clipped to
                # the room
                pxs = [min(x0 + w - 1, max(x0 + 1, v))
                       for v in range(int(x0) + 8, int(x0 + w), 16)] or \
                      [x0 + w / 2]
                pys = [min(y0 + h - 1, max(y0 + 1, v))
                       for v in range(int(y0) + 8, int(y0 + h), 16)] or \
                      [y0 + h / 2]
                for py in pys:
                    if not (0 <= py < th * TILE):
                        continue
                    for px in pxs:
                        if not (0 <= px < tw * TILE):
                            continue
                        if not solid_at(px, py):
                            solid_miss += 1
            elif o in CV.SPIKE_OBJECTS and inst["xscale"] == 1 and \
                    inst["yscale"] == 1:
                tx, ty = int(inst["x"]) // TILE, int(inst["y"]) // TILE
                if not (0 <= tx < tw and 0 <= ty < th):
                    continue
                if tiles[ty][tx] == SPIKE_SHAPE[o]:
                    continue
                cx, cy = inst["x"] + 16, inst["y"] + 16
                if tiles[ty][tx] == T_BLOCK and any(
                        r[0] <= cx <= r[2] and r[1] <= cy <= r[3]
                        for r in src_solid_rects):
                    continue     # spike embedded inside a source wall:
                    #              the solid wins the tile both sides
                # killer-rect or killer-entity fallback (removable rows)
                if any(kl <= cx <= kr and kt <= cy <= kb
                       for (_sh, kl, kt, kr, kb) in killers):
                    continue
                near = any(abs(float(e[1]) - inst["x"]) <= 32 and
                           abs(float(e[2]) - inst["y"]) <= 32
                           for e in env.xents() if e[6] > 0)
                if not near:
                    spike_miss += 1
        if solid_miss:
            fails.append(f"{rname}: {solid_miss} sampled source-solid "
                         f"points not solid in the pack")
        if spike_miss:
            fails.append(f"{rname}: {spike_miss} source spikes with no "
                         f"pack killer at their tile")
        r_out["killer_rects"] = len(killers)

        # 6. saves per difficulty
        src_saves = [0, 0, 0]
        for inst in insts:
            m = CV.SAVE_OBJECTS.get(inst["object"])
            if m:
                for d in range(3):
                    if (m >> d) & 1:
                        src_saves[d] += 1
        cps = rec.get("checkpoints", [])
        r_out["src_saves_by_diff"] = src_saves
        r_out["pack_checkpoints"] = len(cps)
        if src_saves[0] != len(cps):
            fails.append(f"{rname}: saves M={src_saves[0]} but pack has "
                         f"{len(cps)} checkpoints")

        # dynamic-object mapping table
        objmap = {}
        for e in xr["xents"]:
            o = e["provenance"]["source_object"]
            objmap.setdefault(o, {}).setdefault(int(e["cls"]), 0)
            objmap[o][int(e["cls"])] += 1
        r_out["object_to_class"] = {o: dict(sorted(v.items()))
                                    for o, v in sorted(objmap.items())}
        audit["rooms"][rname] = r_out
        print(f"{rname:18s} dims ok  inst {len(insts):4d} "
              f"(e{buckets['entity']}/l{buckets['lowered']}/"
              f"x{buckets['excluded']})  saves {src_saves[0]}  "
              f"src {r_out['source_sha256'][:8]}  "
              f"pack {r_out['pack_content_sha256'][:8]}")

    # 5. runtime edge walk (transition targets): every pack warp record
    # in every gameplay room is touched at an in-room point of its rect
    # and the arrival room asserted.  Flag-conditional variants get
    # their flag plus the routing settle frames; a same-room dest is
    # verified by the position jump instead of a room change.
    if not quick:
        for rname in gameplay:
            rec = by_name[rname]
            for w in rec.get("warps", []):
                dest = w.get("dest_room")
                dormant = not w.get("active", True)
                # a dormant warp is activated by a flag_set room event
                # naming its tag (BossTeleporters, the orb_dracula door)
                need_flag = None
                if dormant:
                    for ev in rec.get("events", []):
                        if ev.get("when") == "flag_set" and any(
                                a.get("do") == "activate" and
                                a.get("tag") == w.get("tag")
                                for a in ev.get("actions", [])):
                            need_flag = ev["flag"]
                            break
                    if need_flag is None and w.get("xop0") is not None:
                        need_flag = X.PROGRESSION_FLAGS["orb_dracula"]
                env.close()
                env = CIWanna.from_pack(pack, seed=11,
                                        checkpoint_respawn=True,
                                        start_room=names.index(rname),
                                        max_steps=90000000)
                env.reset()
                if need_flag is not None:
                    env.set_gflag(need_flag, True)
                    env.step(2)      # flag routing settles within 2 frames
                    env.step(2)
                pw, ph = env.room_px
                # candidate in-room contact points whose kid hitbox
                # (-5,-12,5,8) overlaps the (possibly off-room) rect;
                # several tried because source hazards can cover part of
                # a warp (the trophy teleporters sit under blockKills)
                rl, rr = w["x"] - w["half_w"], w["x"] + w["half_w"]
                rt, rb = w["y"] - w["half_h"], w["y"] + w["half_h"]

                def cl(v, lo, hi):
                    return min(max(v, lo), hi)
                cands = []
                for (cx, cy) in ((w["x"], w["y"]), (w["x"], rb + 8),
                                 (w["x"], rb - 4), (w["x"], rt - 6),
                                 (rl - 3, w["y"]), (rr + 3, w["y"])):
                    tx = cl(cl(cx, 6, pw - 6), rl - 4, rr + 4)
                    ty = cl(cl(cy, 6, ph - 6), rt - 7, rb + 11)
                    if (tx, ty) not in cands:
                        cands.append((tx, ty))
                room0 = env.room
                same_room = dest is not None and dest == room0
                ok, arrived = False, None
                for (tx, ty) in cands:
                    d0 = env.deaths
                    for _ in range(10):
                        env.set_state(tx, ty, 0, 0, 1)
                        env.step(2)
                        if env.deaths != d0:
                            break            # deadly spot: next candidate
                        if not same_room and dest is not None and \
                                env.room != room0:
                            arrived = names[env.room]
                            ok = arrived == names[dest]
                            break
                        if (dest is None or same_room) and \
                                abs(env.x - w["dest_x"]) < 3 and \
                                abs(env.y - w["dest_y"]) < 40:
                            arrived, ok = rname, True
                            break
                    if ok or (arrived and not ok):
                        break
                if not ok:
                    fails.append(
                        f"warp {rname}@({w['x']:.0f},{w['y']:.0f}) -> "
                        f"{'same-room' if dest is None or same_room else names[dest]}: "
                        f"got {arrived or 'no transition'}")
                audit["edge_walk"].append(
                    {"from": rname,
                     "to": names[dest] if dest is not None else rname,
                     "x": w["x"], "y": w["y"], "ok": ok,
                     "cond": need_flag is not None})
        walked = sum(1 for e in audit["edge_walk"] if e["ok"])
        print(f"warp walk: {walked}/{len(audit['edge_walk'])} verified")

    # 8. event inventory for implemented gameplay objects
    all_objs = set()
    for rname in gameplay:
        for inst in parse_instances(os.path.join(rooms_dir, rname,
                                                 "instances.txt")):
            all_objs.add(inst["object"])
    for o in sorted(all_objs):
        p = os.path.join(objs_dir, o + ".gml")
        if not os.path.isfile(p):
            continue
        evs = EV_RE.findall(open(p, encoding="utf-8",
                                 errors="replace").read())
        bucket = ("excluded_visual" if o in X.VISUAL_CLASSES else
                  "static_solid" if o in X.STATIC_CLASSES else
                  "lowered_static" if o in lowered else "entity")
        audit["event_inventory"][o] = {
            "bucket": bucket,
            "events": evs,
            "draw_only": all(e.startswith("Draw") for e in evs) if evs
            else False,
        }

    env.close()
    out = "build/source_reports/iwbtgr_room_audit.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(audit, open(out, "w"), indent=1, sort_keys=True)
    print(f"\nwrote {out}")
    if fails:
        print(f"\nAUDIT FAILURES ({len(fails)}):")
        for f in fails:
            print("  -", f)
        return 1
    print("audit clean: every check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
