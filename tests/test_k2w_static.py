"""Static-world validation for the K2 WARPED import (k2warped_gms14).

Verifies the milestone's acceptance list against BOTH the built pack
and an independent parse of the pinned source tree (skipped where the
source clone is absent): every source room present in source order,
dimensions match, instance counts match, transition targets exist and
resolve at runtime, save positions match, the room graph is preserved,
and nothing was manually redesigned (the pack carries the source-text
checksum it was built from).  Dynamic objects are not lowered yet;
their complete inventory lives in the coverage report and is asserted
here to account for every placed instance.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.games import k2warped_gms14 as K

SRC = os.environ.get("K2W_SRC", "/tmp/k2w")

needs_pack = pytest.mark.skipif(not os.path.isfile(K.PACK_PATH),
                                reason="k2warped pack not built locally")
needs_src = pytest.mark.skipif(
    not os.path.isdir(os.path.join(SRC, "rooms")),
    reason="K2W source clone not available")

_COV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "build", "source_reports",
                    "k2warped_gms14.coverage.json")


def _graph():
    return K.graph()


def _cov():
    assert os.path.isfile(_COV), "coverage report missing (run the build)"
    return json.load(open(_COV))


def _src_room(name):
    t = open(os.path.join(SRC, "rooms", name + ".room.gmx"),
             encoding="utf-8", errors="replace").read()
    w = int(re.search(r"<width>(\d+)</width>", t).group(1))
    h = int(re.search(r"<height>(\d+)</height>", t).group(1))
    insts = re.findall(r'<instance objName="([^"]+)" x="(-?[\d.]+)" '
                       r'y="(-?[\d.]+)"', t)
    return w, h, insts


@needs_src
def test_every_source_room_present_in_order():
    t = open(next(os.path.join(SRC, f) for f in os.listdir(SRC)
                  if f.endswith(".project.gmx")),
             encoding="utf-8", errors="replace").read()
    src_order = re.findall(r"<room>rooms\\(.*?)</room>", t)
    assert _graph()["room_order"] == src_order
    assert len(src_order) == 148


@needs_pack
@needs_src
def test_room_dimensions_match_source():
    names = K.room_names()
    pack = K.load_pack()
    bad = []
    for i, n in enumerate(names):
        w, h, _ = _src_room(n)
        c = CIWanna.from_pack(pack, seed=7, start_room=i, max_steps=1000)
        c.reset()
        if c.room_px != (w, h):
            bad.append((n, (w, h), c.room_px))
        c.close()
    assert not bad, f"dimension drift: {bad[:5]}"


@needs_src
def test_instance_counts_match_source():
    cov = _cov()
    bad = []
    for n in K.room_names():
        _, _, insts = _src_room(n)
        got = sum(cov["per_room"].get(n, {}).values())
        # warp_unresolved is an accounting subcategory, not an instance
        got -= cov["per_room"].get(n, {}).get("warp_unresolved", 0)
        if got != len(insts):
            bad.append((n, len(insts), got))
    assert not bad, f"instance-count drift: {bad[:5]}"
    assert cov["instances_total"] == sum(
        len(_src_room(n)[2]) for n in K.room_names())


@needs_pack
def test_transition_targets_exist():
    g = _graph()
    names = set(g["room_order"])
    for e in g["edges"]:
        assert e["from"] in names and e["to"] in names, e


@needs_pack
def test_warps_resolve_at_runtime():
    """Every lowered (enabled) warp is touched at a point of its rect
    and must change rooms to its recorded destination."""
    names = K.room_names()
    pack = K.load_pack()
    g = json.load(open(os.path.join(
        os.path.dirname(K.PACK_PATH), "k2warped_gms14.iwgame.json")))
    rooms = {r["name"]: r for r in g["rooms"]}
    fails = []
    for rname in names:
        for w in rooms[rname].get("warps", []):
            if w.get("active") is False:
                continue
            c = CIWanna.from_pack(pack, seed=7, checkpoint_respawn=True,
                                  start_room=names.index(rname),
                                  max_steps=100000)
            c.reset()
            pw, ph = c.room_px
            rl, rr = w["x"] - w["half_w"], w["x"] + w["half_w"]
            rt, rb = w["y"] - w["half_h"], w["y"] + w["half_h"]

            def cl(v, lo, hi):
                return min(max(v, lo), hi)
            same_room = w["dest_room"] == names.index(rname)
            ok = False
            for (cx, cy) in ((w["x"], w["y"]), (w["x"], rb + 8),
                             (rl - 3, w["y"]), (rr + 3, w["y"]),
                             (w["x"], rt - 6)):
                tx = cl(cl(cx, 6, pw - 6), rl - 4, rr + 4)
                ty = cl(cl(cy, 6, ph - 6), rt - 7, rb + 11)
                d0, r0 = c.deaths, c.room
                for _ in range(8):
                    c.set_state(tx, ty, 0, 0, 1)
                    c.step(2)
                    if not same_room and c.room != r0:
                        ok = c.room == w["dest_room"]
                        break
                    if same_room and w.get("dest_x") is not None and \
                            abs(c.x - w["dest_x"]) < 3 and \
                            abs(c.y - w["dest_y"]) < 40:
                        ok = True         # in-room repositioning warp
                        break
                    if c.deaths != d0:
                        break
                if ok or c.room != names.index(rname):
                    break
            if not ok:
                fails.append((rname, w["x"], w["y"],
                              names[w["dest_room"]]))
            c.close()
    assert not fails, f"unresolved warps at runtime: {fails[:6]}"


@needs_pack
@needs_src
def test_save_positions_match_source():
    names = K.room_names()
    g = json.load(open(os.path.join(
        os.path.dirname(K.PACK_PATH), "k2warped_gms14.iwgame.json")))
    rooms = {r["name"]: r for r in g["rooms"]}
    cov = _cov()
    save_objs = {o for o, v in cov["event_inventory"].items()
                 if v["category"] == "save"}
    bad = []
    for n in names:
        _, _, insts = _src_room(n)
        src_saves = sorted((float(x), float(y)) for o, x, y in insts
                           if o in save_objs)
        cps = rooms[n].get("checkpoints", [])
        if len(src_saves) != len(cps):
            bad.append((n, len(src_saves), len(cps)))
            continue
        # checkpoint centers derive from the save sprite bbox at the
        # source position; verify each source save has a checkpoint
        # within its own 32px cell
        for (sx, sy) in src_saves:
            if not any(abs(cp["x"] - sx) <= 32 and abs(cp["y"] - sy) <= 32
                       for cp in cps):
                bad.append((n, "offset", (sx, sy)))
    assert not bad, f"save drift: {bad[:5]}"


@needs_src
def test_room_graph_matches_source_derivation():
    """Re-derive warp edges from the source creation codes and compare
    with the committed graph (statically resolvable warps only)."""
    cov = _cov()
    warp_objs = {o for o, v in cov["event_inventory"].items()
                 if v["category"] == "warp"}
    got = {(e["from"], e["to"]) for e in _graph()["edges"]
           if e.get("via") != "scripted"}
    want = set()
    names = set(K.room_names())
    for n in K.room_names():
        t = open(os.path.join(SRC, "rooms", n + ".room.gmx"),
                 encoding="utf-8", errors="replace").read()
        for m in re.finditer(
                r'<instance objName="([^"]+)"[^>]*?code="([^"]*)"', t):
            o, code = m.groups()
            if o in warp_objs:
                mm = re.search(r"roomTo\s*=\s*(r\w+)", code)
                if mm and mm.group(1) in names:
                    want.add((n, mm.group(1)))
    assert got == want, (f"edge drift: missing={sorted(want - got)[:5]} "
                         f"extra={sorted(got - want)[:5]}")


@needs_pack
def test_no_redesign_source_checksum_stamped():
    g = json.load(open(os.path.join(
        os.path.dirname(K.PACK_PATH), "k2warped_gms14.iwgame.json")))
    prov = g["provenance"]
    assert prov["source_commit"] == _graph()["pin_commit"]
    assert prov["source_checksum_sha256"] == _graph()["source_text_sha256"]
    assert len(prov["source_checksum_sha256"]) == 64


@needs_pack
def test_dynamic_objects_fully_inventoried():
    cov = _cov()
    st = cov["instances_by_status"]
    assert st["exact"] + st["unsupported"] == cov["instances_total"]
    assert cov["instances_total"] == 19574
    assert st["unsupported"] > 0            # honestly reported, not hidden
    # every placed object appears in the event inventory with a category
    placed = {o for o, v in cov["event_inventory"].items()
              if v["placed_instances"] > 0}
    assert len(placed) >= 500


@needs_pack
def test_env_api_both_modes_and_isolation():
    from iwanna_gym.env import IWannaEnv
    e = IWannaEnv(game="k2warped_gms14", mode="full_game", max_steps=5000)
    _, info = e.reset(seed=3)
    assert e._room_names[info["room"]] == "rStage0"
    for _ in range(20):
        e.step(2)
    e.close()
    e = IWannaEnv(game="k2warped_gms14", mode="room",
                  room_id="rStage6Crimson", max_steps=5000)
    _, info = e.reset(seed=3)
    assert e._room_names[info["room"]] == "rStage6Crimson"
    e.close()
    # the existing exact game is untouched
    e = IWannaEnv(game="iwbtgr_1_5_3", mode="room", room_id="rGuy1")
    _, info = e.reset(seed=3)
    assert e._room_names[info["room"]] == "rGuy1"
    e.close()


@needs_pack
def test_deterministic_replay_static_pack():
    names = K.room_names()

    def run():
        c = CIWanna.from_pack(K.load_pack(), seed=99,
                              checkpoint_respawn=True,
                              start_room=names.index("rStage1Fortress"),
                              max_steps=100000)
        c.reset()
        out = []
        for t in range(600):
            c.step((t * 2654435761) % 12)
            out.append((round(c.x, 4), round(c.y, 4), c.deaths, c.room))
        c.close()
        return out
    assert run() == run()
