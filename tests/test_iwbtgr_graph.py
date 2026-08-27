"""Room-graph validation for iwbtgr_1_5_3 (committed metadata; runs
without the pack or source)."""
from __future__ import annotations

from iwanna_gym.games import iwbtgr_1_5_3 as G


def _g():
    return G.graph()


def test_every_transition_targets_a_valid_room():
    g = _g()
    names = set(g["room_order"])
    for e in g["edges"]:
        assert e["from"] in names, e
        assert e["to"] in names, e
        assert e["via"] in ("warp", "EntranceTele"), e


def test_edge_geometry_and_modes():
    g = _g()
    modes = {"absolute", "offset", "target_start", "absolute_keep",
             "x_abs_y_off", "x_off_y_abs"}
    for e in g["edges"]:
        assert e["mode"] in modes, e
        assert e["half_w"] > 0 and e["half_h"] > 0, e
        room = next(r for r in g["rooms"] if r["name"] == e["from"])
        # warp strips may sit just outside the playable area (edge strips)
        assert -64 <= e["x"] <= room["px"][0] + 64, e
        assert -64 <= e["y"] <= room["px"][1] + 64, e


def test_conditional_edges_are_explicit():
    g = _g()
    conds = [e for e in g["edges"] if e["condition"]]
    assert any(e["condition"].get("savedata") == "orb_dracula" for e in conds)
    gate = [e for e in conds if e["via"] == "EntranceTele"]
    assert len(gate) == 1
    assert gate[0]["from"] == "rGuyEntrance" and gate[0]["to"] == "rGuyRoad"
    assert sorted(gate[0]["condition"]["all_of"]) == sorted(
        ["orb_tyson", "orb_birdo", "orb_kraidgief", "orb_bowser",
         "orb_mother", "orb_dracula"])
    assert gate[0]["lowered"] is False   # AND-gate: visible, not guessed


def test_no_orphaned_required_rooms():
    g = _g()
    assert g["orphaned_required_rooms"] == []
    # the flag-free playable region reaches the pre-palace world
    now = set(g["reachable_without_flags"])
    for must in ("rGuy1", "rZelda", "rGraveyard", "rMegaman", "rMetroid",
                 "rFactoryOutskirts", "rCastlevania", "rDraculaBoss",
                 "rKraidgiefLair", "rKraidgiefBoss", "rBowserBoss",
                 "rMechaBirdoBoss", "rGuyEntrance"):
        assert must in now, must
    # the palace is flag/script-gated but connected
    all_r = set(g["reachable_with_all_flags_and_scripts"])
    for must in ("rGuyRoad", "rGuyFortress1", "rGuyLabyrinth",
                 "rGuyFortress2", "rGuyTower", "rGuyBoss", "rEnding"):
        assert must in all_r, must


def test_save_respawn_rooms_exist():
    g = _g()
    # every room with saves is a real room; totals decrease with difficulty
    tot = {"medium": 0, "hard": 0, "very_hard": 0, "impossible": 0}
    for r in g["rooms"]:
        for k, v in r["saves_by_difficulty"].items():
            assert v >= 0
            tot[k] += v
    assert tot["medium"] >= tot["hard"] >= tot["very_hard"] >= tot["impossible"]
    assert tot["impossible"] == 0        # source: all saves destroyed on diff 3
    # source counts: 23 saveMedium + 27 saveHard + 22 saveVeryHard +
    # 3 saveVeryEvil placements
    assert tot["medium"] == 75 and tot["hard"] == 52 and tot["very_hard"] == 25


def test_progression_flags_stable():
    g = _g()
    assert g["progression_flags"] == {
        "orb_tyson": 1, "orb_birdo": 2, "orb_kraidgief": 3, "orb_bowser": 4,
        "orb_mother": 5, "orb_dracula": 6, "orb_dragon": 7, "orb_guy": 8}


def test_adjacency_is_inspectable_offline():
    """The machine-readable adjacency report needs no runtime."""
    g = _g()
    adj = {}
    for e in g["edges"]:
        adj.setdefault(e["from"], set()).add(e["to"])
    assert adj["rGuy1"] == {"rZelda", "rMegaman", "rKraidgiefLair"}
    assert "rCastlevania" in adj["rFactoryOutskirts"]
    assert adj["rGuyTower"] == {"rGuyBoss"}
