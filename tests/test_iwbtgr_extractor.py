"""Tests for the gm82save reader and the IWBTGR source-inventory extractor.

Two layers:

* the committed mini fixture (tests/fixtures/gm82_mini — original content)
  exercises the format reader and inventory mechanics deterministically;
* when a real IWBTGR source tree is supplied locally (IWBTGR_SRC env var,
  or the default /tmp/iwbtgr-mod checkout), a consistency suite runs
  against it: every room inventoried, every instance accounted for, no
  code bodies leaked into the committed report shape. The source tree is
  never committed (third_party/SOURCES.md).
"""
from __future__ import annotations

import os

import pytest

from tools.importers.iwbtgr import (
    build_inventory,
    detect,
    load_project,
    resolve_root,
)
from tools.importers.iwbtgr.gm82 import parse_events
from tools.importers.iwbtgr.inventory import _parse_warp_assigns
from tools.importers.iwbtgr.mapping import STATUSES

HERE = os.path.dirname(os.path.abspath(__file__))
MINI = os.path.join(HERE, "fixtures", "gm82_mini")
REAL = os.environ.get("IWBTGR_SRC", "/tmp/iwbtgr-mod")


# ------------------------------------------------------------- format reader

def test_mini_project_loads():
    p = load_project(MINI)
    assert p.settings["gm82_version"] == 5
    assert p.settings["exe_description"] == "gm82_mini test fixture"
    assert set(p.objects) == {"objSolid", "objDeco", "objChild"}
    assert p.room_order == ["rOne"]
    assert set(p.scripts) == {"helper"}
    assert p.sprites["sprDot"].frame_count == 1
    assert len(p.sprites["sprDot"].frame_sha256[0]) == 64


def test_mini_object_properties_and_events():
    p = load_project(MINI)
    o = p.objects["objSolid"]
    assert o.solid and not o.visible and o.depth == 100
    assert [e.name for e in o.events] == ["Create_0", "Step_0"]
    assert "room_goto(rOne)" in o.event("Step_0").code
    assert p.parent_chain("objChild") == ["objSolid"]


def test_mini_room_numbers_are_verbatim():
    """Source numeric values survive exactly — no tile-grid snapping."""
    p = load_project(MINI)
    r = p.rooms["rOne"]
    assert (r.width, r.height, r.speed) == (800, 608, 50)
    xs = [(i.object, i.x, i.y) for i in r.instances]
    assert ("objSolid", 96.0, 543.5) in xs          # non-multiple-of-32 y
    assert ("objDeco", 128.25, 200.0) in xs         # fractional x preserved
    deco = [i for i in r.instances if i.object == "objDeco"][0]
    assert (deco.xscale, deco.yscale, deco.angle) == (2.0, 1.5, 90.0)
    assert len(r.tiles) == 2 and r.tile_layers == {1000: 2}
    assert r.tiles[0].u == 0 and r.tiles[0].width == 32
    assert r.creation_code.strip() == "global.testflag=0"


def test_mini_instance_creation_code_and_warp_parse():
    p = load_project(MINI)
    r = p.rooms["rOne"]
    coded = [i for i in r.instances if i.creation_code]
    assert len(coded) == 1
    w = _parse_warp_assigns(coded[0].creation_code)
    assert w == {"roomTo": "rOne", "warpX": 224, "warpYvoff": -32}


def test_parse_events_splits_sections():
    evs = parse_events("#define Create_0\na=1\n#define Collision_block\nb=2\n")
    assert [(e.name, e.code) for e in evs] == [("Create_0", "a=1"),
                                               ("Collision_block", "b=2")]


# ---------------------------------------------------------------- inventory

def test_mini_inventory_consistency():
    rep = build_inventory(MINI)
    c = rep["counts"]
    assert c["rooms"] == 1
    assert c["object_definitions"] == 3
    assert c["object_instances"] == 3
    assert c["tiles"] == 2
    room = rep["rooms"][0]
    assert room["instance_count"] == len(room["instances"]) == 3
    # nothing dropped: every instance's object exists in the object table
    names = {o["name"] for o in rep["objects"]}
    assert all(i["object"] in names for i in room["instances"])
    # statuses always one of the five
    assert all(o["semantic"]["status"] in STATUSES for o in rep["objects"])
    # code metadata preserved, bodies excluded by default
    solid = [o for o in rep["objects"] if o["name"] == "objSolid"][0]
    assert solid["event_count"] == 2
    assert all("code" not in e for e in solid["events"])
    assert solid["room_goto_targets"] == ["rOne"]
    # warp parse surfaced on the instance
    coded = [i for i in room["instances"] if "parsed_warp" in i][0]
    assert coded["parsed_warp"]["roomTo"] == "rOne"
    assert rep["room_graph"]["warp_edges"][0]["to"] == "rOne"
    # globals inventoried
    assert "testflag" in rep["global_variables"]
    # reproducibility: same input -> identical report
    assert build_inventory(MINI) == rep


def test_mini_with_code_flag_embeds_bodies():
    rep = build_inventory(MINI, with_code=True)
    solid = [o for o in rep["objects"] if o["name"] == "objSolid"][0]
    assert any("room_goto" in e.get("code", "") for e in solid["events"])


# ------------------------------------------------- real source (if supplied)

needs_real = pytest.mark.skipif(
    not detect(REAL), reason="IWBTGR source tree not supplied "
                             "(set IWBTGR_SRC to the checkout)")


@needs_real
def test_real_source_full_coverage():
    rep = build_inventory(resolve_root(REAL))
    c = rep["counts"]
    # every room dir appears; instance totals add up exactly
    assert c["rooms"] == len(rep["rooms"]) > 0
    assert c["object_instances"] == sum(r["instance_count"]
                                        for r in rep["rooms"])
    assert all(r["instance_count"] == len(r["instances"])
               for r in rep["rooms"])
    # every placed object is in the object table (nothing unaccounted)
    names = {o["name"] for o in rep["objects"]}
    missing = {i["object"] for r in rep["rooms"] for i in r["instances"]} - names
    assert not missing, missing
    # every object/event classified into one of the five statuses
    assert all(o["semantic"]["status"] in STATUSES for o in rep["objects"])
    # all creation code and events accounted for (hash + lines, or parsed)
    cov = rep["code_coverage"]
    assert cov["object_events_preserved_metadata"] == cov["object_events_total"]
    # provenance recorded
    assert rep["source"]["tree_sha256"]
    assert rep["source"]["project_settings"]["exe_version"] == "1.5.3.0"
    # committed-report shape: no GML bodies
    import json
    assert '"code":' not in json.dumps(rep)


@needs_real
def test_real_source_known_landmarks():
    """A few structural facts read straight from the source (not from
    memory): the game starts at rInit, the player object exists with the
    sprMask collision mask, and the warp graph connects rGuy1 onward."""
    rep = build_inventory(resolve_root(REAL))
    assert rep["room_graph"]["start_room"] == "rInit"
    player = [o for o in rep["objects"] if o["name"] == "player"][0]
    assert player["mask"] == "sprMask"
    assert player["persistent"] is True
    outgoing = {e["from"] for e in rep["room_graph"]["warp_edges"]}
    assert "rGuy1" in outgoing
