"""Static-world import validation for iwbtgr_1_5_3.

Committed-metadata checks (graph/manifest structure) always run. Checks
needing the compiled pack or the source tree auto-skip when those are not
supplied locally (IWBTGR_SRC / built pack), per third_party/SOURCES.md.
"""
from __future__ import annotations

import json
import os

import pytest

from iwanna_gym.games import iwbtgr_1_5_3 as G

REAL = os.environ.get("IWBTGR_SRC", "/tmp/iwbtgr-mod")
HAVE_PACK = os.path.isfile(G.PACK_PATH)
HAVE_SRC = os.path.isdir(os.path.join(REAL, "IWBTGR Source Files"))

needs_pack = pytest.mark.skipif(not HAVE_PACK, reason="pack not built locally")
needs_src = pytest.mark.skipif(not (HAVE_PACK and HAVE_SRC),
                               reason="source tree not supplied")


def _graph():
    return G.graph()


# ------------------------------------------------- committed metadata only

def test_graph_room_ids_stable_and_unique():
    g = _graph()
    names = g["room_order"]
    assert len(names) == len(set(names)) == 27
    ids = [r["id"] for r in g["rooms"]]
    assert ids == list(range(27))
    assert [r["name"] for r in g["rooms"]] == names
    assert g["start_room_full_game"] in names


def test_manifest_matches_graph():
    m = G.manifest()
    g = _graph()
    assert m["room_order"] == g["room_order"]
    assert m["tested_source"]["tree_sha256"] == g["source_tree_sha256"]
    assert m["progression_flags"] == g["progression_flags"]


# ----------------------------------------------------- pack-backed checks

@needs_pack
def test_all_rooms_load_natively_with_exact_dims():
    from iwanna_gym.clib import CIWanna
    pack = G.load_pack()
    g = _graph()
    for r in g["rooms"]:
        c = CIWanna.from_pack(pack, start_room=r["id"])
        c.reset()
        assert c.room == r["id"]
        assert list(c.room_px) == r["px"], r["name"]
        assert (c.tw, c.th) == tuple(r["tiles"]), r["name"]
        if r["start"]:
            assert (c.x, c.y) == tuple(r["start"]), r["name"]
        c.close()


@needs_pack
def test_env_full_game_and_room_modes():
    import iwanna_gym as iw
    g = _graph()
    env = iw.IWannaEnv(game="iwbtgr_1_5_3", mode="full_game")
    _, info = env.reset(seed=0)
    assert info["room"] == g["room_order"].index(g["start_room_full_game"])
    env.close()
    env = iw.IWannaEnv(game="iwbtgr_1_5_3", mode="room",
                       room_id="rGuyLabyrinth", difficulty="hard")
    _, info = env.reset(seed=0)
    assert info["room"] == g["room_order"].index("rGuyLabyrinth")
    env.close()
    with pytest.raises(KeyError):
        iw.IWannaEnv(game="iwbtgr_1_5_3", mode="room", room_id="rNope")


@needs_pack
def test_difficulty_saves_match_graph_counts():
    from iwanna_gym.clib import CIWanna
    pack = G.load_pack()
    g = _graph()
    for r in g["rooms"]:
        for diff, dname in ((0, "medium"), (1, "hard"),
                            (2, "very_hard"), (3, "impossible")):
            c = CIWanna.from_pack(pack, start_room=r["id"], difficulty=diff)
            c.reset()
            ents = c.entities()
            active_saves = int((ents[:, 0] == 8).sum()) if len(ents) else 0
            assert active_saves == r["saves_by_difficulty"][dname], \
                (r["name"], dname)
            c.close()


@needs_pack
def test_warp_traversal_and_target_start():
    """rGuy1 right edge -> rZelda, arriving at rZelda's playerStart+(17,23)
    (the exact source spawn rule)."""
    from iwanna_gym.clib import CIWanna
    pack = G.load_pack()
    g = _graph()
    names = g["room_order"]
    c = CIWanna.from_pack(pack, start_room=names.index("rGuy1"))
    c.reset()
    c.set_state(4796, 1232)
    prev = c.room
    for _ in range(10):
        c.step(4)
        if c.room != prev:
            break
    assert names[c.room] == "rZelda"
    z = next(r for r in g["rooms"] if r["name"] == "rZelda")
    assert (c.x, c.y) == tuple(z["start"])
    assert c.room_transitions == 1
    c.close()


@needs_pack
def test_conditional_warp_orb_dracula():
    from iwanna_gym.clib import CIWanna
    pack = G.load_pack()
    g = _graph()
    names = g["room_order"]
    i_f = names.index("rFactoryOutskirts")

    c = CIWanna.from_pack(pack, start_room=i_f)
    c.reset()
    c.set_state(2740, 570)
    for _ in range(10):
        c.step(2)
        if c.room != i_f:
            break
    assert names[c.room] == "rCastlevania"
    c.close()

    c = CIWanna.from_pack(pack, start_room=i_f)
    c.reset()
    c.set_gflag(g["progression_flags"]["orb_dracula"], True)
    c.step(2), c.step(2)          # flag routing settles within 2 frames
    c.set_state(2740, 570)
    for _ in range(10):
        c.step(2)
        if abs(c.x - 3040) < 2:
            break
    assert names[c.room] == "rFactoryOutskirts" and c.x == 3040
    c.close()


@needs_pack
def test_deterministic_replay_full_game():
    from iwanna_gym.clib import CIWanna
    pack = G.load_pack()

    def run():
        c = CIWanna.from_pack(pack, seed=77, checkpoint_respawn=True)
        c.reset()
        traj = []
        for t in range(800):
            c.step((t * 5 + 1) % 6)
            traj.append((c.x, c.y, c.vspeed, c.room, c.deaths))
        c.close()
        return traj

    assert run() == run()


# ------------------------------------------- source-reconciliation checks

@needs_src
def test_import_reconciles_with_source_recount():
    """Instance accounting: imported + excluded == every instance in the
    source; coordinates preserved verbatim for spot instances."""
    cov = json.load(open(os.path.join(G.BUILD_DIR,
                                      G.GAME_ID + ".coverage.json")))
    t = cov["totals"]
    assert t["instances_imported"] + t["instances_excluded"] \
        == t["instances_in_source"] == 8212
    # nothing silently dropped: every excluded object carries a reason
    for obj in cov["excluded_by_object"]:
        assert obj in cov["excluded_reasons"] or obj == "EntranceTele"

    from tools.importers.iwbtgr.gm82 import load_project
    proj = load_project(os.path.join(REAL, "IWBTGR Source Files"))
    # spot-check exact source coordinates -> runtime geometry
    from iwanna_gym.clib import CIWanna
    pack = G.load_pack()
    g = _graph()
    names = g["room_order"]
    room = proj.rooms["rGuy1"]
    c = CIWanna.from_pack(pack, start_room=names.index("rGuy1"))
    c.reset()
    tiles = c.tiles()
    blocks = [i for i in room.instances if i.object == "block"
              and i.xscale == 1 and i.yscale == 1
              and i.x % 32 == 0 and i.y % 32 == 0][:50]
    assert blocks
    for b in blocks:
        assert tiles[int(b.y) // 32][int(b.x) // 32] == 1, (b.x, b.y)
    spikes = [i for i in room.instances if i.object == "spikeUp"
              and i.x % 32 == 0 and i.y % 32 == 0][:50]
    for s in spikes:
        assert tiles[int(s.y) // 32][int(s.x) // 32] == 2, (s.x, s.y)
    c.close()


@needs_src
def test_graph_regenerates_identically_from_source():
    from iwanna_gym.games.iwbtgr_1_5_3.converter import convert
    res = convert(os.path.join(REAL, "IWBTGR Source Files"))
    assert res["graph"] == _graph()
