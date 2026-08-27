"""End-to-end tests for the game-import pipeline (docs/importer_architecture.md):

    synthetic source fixture -> extractor -> canonical IR (.iwgame.json)
      -> validator -> binary compiler (.iwpack) -> native loading
      -> multi-room stepping (warp + edge transitions, global flag, gate)
      -> deterministic replay

The committed fixture (tests/fixtures/synthetic_src) is original synthetic
content — no third-party game data.
"""
from __future__ import annotations

import json
import os
import struct
import tempfile

import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.gamepack import (
    compile_pack,
    load_iwgame,
    mapping_report,
    save_iwgame,
    validate,
)
from iwanna_gym.gamepack.compilepack import CompileError, PACK_MAGIC
from iwanna_gym.levels import load_level
from tools.importers import detect_importer, synthetic

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "synthetic_src")
FIXTURE_UNKNOWN = os.path.join(HERE, "fixtures", "synthetic_src_unknown")


def _extract():
    return synthetic.extract(FIXTURE, game_id="fixture_quest")


def _pack_bytes():
    return compile_pack(_extract()).data


# ---------------------------------------------------------------- extraction

def test_detect_and_extract():
    assert detect_importer(FIXTURE) is synthetic
    doc = _extract()
    assert doc["metadata"]["game_id"] == "fixture_quest"
    assert len(doc["rooms"]) == 2
    assert doc["room_graph"]["start_room"] == 0
    # room graph records both the warp and the edge links
    kinds = {tuple(e) for e in doc["room_graph"]["edges"]}
    assert (0, 1, "warp") in kinds
    assert (1, 0, "edge_left") in kinds
    # completion is reach_goal in room 1 (the only room with a goal)
    assert doc["completion"] == {"type": "reach_goal", "room": 1}


def test_provenance_recorded_per_element():
    doc = _extract()
    assert doc["provenance"]["importer"] == "synthetic"
    assert len(doc["provenance"]["source_checksum_sha256"]) == 64
    rm_a = doc["rooms"][0]
    warp = [i for i in rm_a["instances"] if i["object"] == "sWarp"][0]
    prov = warp["provenance"]
    assert prov["source_room"] == "rmA"
    assert prov["source_object"] == "sWarp"
    assert prov["source_instance"] == 6
    ev = rm_a["events"][0]
    assert ev["provenance"]["source_event"] == "evUnlock"


def test_statuses_are_honest():
    doc = _extract()
    rep = validate(doc)
    assert rep.ok, rep.text()
    # the moving platform is a documented equivalence, not "exact"
    assert rep.status_counts.get("equivalent", 0) >= 1
    plat = [i for i in doc["rooms"][0]["instances"]
            if i["object"] == "sMovingPlatform"][0]
    assert plat["mapping_status"] == "equivalent"
    assert plat["notes"]


# ---------------------------------------------------------------- validation

def test_unknown_source_content_fails_validation():
    doc = synthetic.extract(FIXTURE_UNKNOWN)
    rep = validate(doc)
    assert not rep.ok
    assert any("sMysteryOrb" in e for e in rep.errors)
    assert any("boss_pattern" in e for e in rep.errors)
    # inspection mode: same items become warnings, never dropped silently
    rep2 = validate(doc, allow_unsupported=True)
    assert rep2.ok
    assert any("sMysteryOrb" in w for w in rep2.warnings)


def test_unknown_source_content_fails_compile_and_drops_visibly():
    doc = synthetic.extract(FIXTURE_UNKNOWN)
    with pytest.raises(CompileError):
        compile_pack(doc)
    res = compile_pack(doc, allow_unsupported=True)
    assert any("sMysteryOrb" in d for d in res.dropped)
    meta = _meta(res.data)
    assert meta["incomplete"] is True
    assert any("sMysteryOrb" in d for d in meta["dropped"])


def test_wrong_physics_profile_rejected():
    doc = _extract()
    doc["physics_profile"] = "iwbtg_original_2007"   # not implemented
    rep = validate(doc)
    assert not rep.ok


# ----------------------------------------------------------------- compiling

def _meta(data: bytes) -> dict:
    hdr = struct.unpack("<20I", data[:80])
    return json.loads(data[hdr[15]:hdr[15] + hdr[16]])


def test_compile_header_and_meta():
    data = _pack_bytes()
    hdr = struct.unpack("<20I", data[:80])
    assert hdr[0] == PACK_MAGIC
    assert hdr[1] == 2          # iwpack format v2
    assert hdr[2] == len(data)
    assert hdr[3] == 2          # rooms
    assert hdr[4] == 0          # start room
    meta = _meta(data)
    assert meta["provenance"]["source_game"] == "Fixture Quest"
    assert meta["incomplete"] is False
    # per-element provenance survives conversion into the pack itself
    wheres = {e["where"]: e for e in meta["elements"]}
    key = [w for w in wheres if "sWarp" in w and "instances" in w][0]
    assert wheres[key]["provenance"]["source_room"] == "rmA"


def test_iwgame_json_roundtrip():
    doc = _extract()
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "f.iwgame.json")
        save_iwgame(doc, p)
        doc2 = load_iwgame(p)
    assert doc2 == json.loads(json.dumps(doc))  # identical modulo json types
    assert compile_pack(doc2).data == compile_pack(doc).data
    assert "fixture_quest" in mapping_report(doc2)


# ------------------------------------------------------------ native runtime

def _scripted(c: CIWanna, max_steps: int = 3000, jump_rooms=(0, 1)):
    """Run right; scripted full jumps over the two spike obstacles."""
    jump = 0
    events = []
    for t in range(max_steps):
        x, room = c.x, c.room
        if jump == 0 and c.on_ground:
            if room == 0 and 0 in jump_rooms and 210 <= x <= 222:
                jump = 20
            if room == 1 and 1 in jump_rooms and 295 <= x <= 310:
                jump = 18
        a = 5 if jump > 0 else 4
        if jump > 0:
            jump -= 1
        c.step(a)
        if c.room != room:
            events.append(("room", room, c.room, c.gflags))
        if c.last_event == 2:
            events.append(("goal",))
            break
        if c.last_event == 1:
            events.append(("death", round(x, 1)))
    return events


def test_pack_loads_and_completes():
    c = CIWanna.from_pack(_pack_bytes(), seed=3, checkpoint_respawn=True)
    c.reset()
    assert c.num_rooms == 2
    assert c.room == 0
    assert (c.tw, c.th) == (20, 12)
    assert (round(c.x), round(c.y)) == (80, 343)   # sPlayerStart
    events = _scripted(c)
    # flag was set by the region event BEFORE warping (gflags bit 1)
    room_moves = [e for e in events if e[0] == "room"]
    assert room_moves[0][1:3] == (0, 1), events     # warp rmA -> rmB
    assert room_moves[0][3] == 2, "flag 1 must be set before the warp"
    assert ("goal",) in events, events              # gate opened, goal reached
    c.close()


def test_room_transition_via_warp_and_edge():
    c = CIWanna.from_pack(_pack_bytes(), seed=5, checkpoint_respawn=True)
    c.reset()
    _scripted(c, jump_rooms=(0,), max_steps=170)    # just get through the warp
    assert c.room == 1
    assert c.room_transitions == 1
    # walk LEFT off rmB's open edge -> back into rmA through the wall gap
    for _ in range(200):
        c.step(0)
        if c.room == 0:
            break
    assert c.room == 0
    assert c.room_transitions == 2
    assert c.gflags == 2, "global flags persist across room transitions"
    assert c.x > 600, "edge entry is at the right side of rmA"
    c.close()


def test_save_respawn_across_rooms():
    c = CIWanna.from_pack(_pack_bytes(), seed=9, checkpoint_respawn=True)
    c.reset()
    _scripted(c, jump_rooms=(0,), max_steps=170)    # touch save, warp to rmB
    assert c.room == 1
    assert c.respawn_room == 0
    deaths0 = c.deaths
    # run right into rmB's spike without jumping -> die -> respawn at the
    # save point back in rmA (fangame checkpoint semantics)
    for _ in range(300):
        c.step(4)
        if c.deaths > deaths0:
            break
    assert c.deaths == deaths0 + 1
    assert c.room == 0
    assert (round(c.x), round(c.y)) == (176, 343)   # the sSave position
    assert c.gflags == 2, "progression flags survive death"
    c.close()


def test_unsupported_pack_data_rejected():
    with pytest.raises(ValueError, match="magic"):
        CIWanna.from_pack(b"NOTAPACK" + b"\0" * 100)
    data = _pack_bytes()
    with pytest.raises(ValueError):
        CIWanna.from_pack(data[: len(data) // 2])   # truncated


def test_deterministic_replay_pack():
    def run():
        c = CIWanna.from_pack(_pack_bytes(), seed=1234, checkpoint_respawn=True)
        c.reset()
        traj = []
        jump = 0
        for t in range(1200):
            x, room = c.x, c.room
            if jump == 0 and c.on_ground and room == 0 and 210 <= x <= 222:
                jump = 20
            a = 5 if jump > 0 else 4
            if jump > 0:
                jump -= 1
            c.step(a)
            traj.append((c.x, c.y, c.vspeed, c.room, c.gflags,
                         c.deaths, c.room_transitions, c.ent_count))
        c.close()
        return traj

    assert run() == run()


def test_classic_levels_unaffected():
    """The classic single-room path must behave exactly as before."""
    text = load_level("traps/t20_finale")

    def run(seed):
        c = CIWanna(text, seed=seed)
        c.reset()
        traj = []
        for t in range(1500):
            c.step((t * 7 + 3) % 6)
            traj.append((c.x, c.y, c.vspeed, c.ent_count, int(c.term[0])))
        c.close()
        return traj

    t1, t2 = run(42), run(42)
    assert t1 == t2
    # classic mode reports single-room defaults through the new accessors
    c = CIWanna(text, seed=1)
    c.reset()
    assert c.num_rooms == 1
    assert c.room == 0
    assert c.gflags == 0
    c.close()
