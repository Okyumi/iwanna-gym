"""iwbtgr_1_5_3 — I Wanna Be The Guy: Remastered 1.5.3, static world.

Committed here: the converter, the room-graph JSON (derived structural
metadata), and the build manifest. NOT committed: the source tree, the IR,
and the compiled pack — they are built locally from a user-supplied source
checkout (manifest.json has the pins and the exact commands), matching the
redistribution policy in third_party/SOURCES.md.

    # one-time local build (source: the autosplitter-mod checkout or the
    # unpacked official IWBTGR Source 1.5.3.zip)
    python -m iwanna_gym.games.iwbtgr_1_5_3 build /path/to/source

    # then
    env = iwanna_gym.IWannaEnv(game="iwbtgr_1_5_3", mode="full_game")
    env = iwanna_gym.IWannaEnv(game="iwbtgr_1_5_3", mode="room",
                               room_id="rGuyLabyrinth", difficulty="hard")
"""
from __future__ import annotations

import json
import os

GAME_ID = "iwbtgr_1_5_3"
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
BUILD_DIR = os.path.join(_REPO, "build", "games")
PACK_PATH = os.path.join(BUILD_DIR, GAME_ID + ".iwpack")
IR_PATH = os.path.join(BUILD_DIR, GAME_ID + ".iwgame.json")
GRAPH_PATH = os.path.join(_HERE, "room_graph.json")
MANIFEST_PATH = os.path.join(_HERE, "manifest.json")

DIFFICULTIES = {"medium": 0, "hard": 1, "very_hard": 2, "impossible": 3}


def graph() -> dict:
    """The committed room graph (inspectable without any runtime)."""
    with open(GRAPH_PATH, encoding="utf-8") as f:
        return json.load(f)


def manifest() -> dict:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def room_names() -> list[str]:
    return graph()["room_order"]


def room_index(room_id: str | int) -> int:
    if isinstance(room_id, int):
        return room_id
    names = room_names()
    if room_id not in names:
        raise KeyError(f"unknown room {room_id!r}; rooms: {names}")
    return names.index(room_id)


def load_pack(path: str | None = None) -> bytes:
    """Compiled pack bytes for env construction (no source parsing here)."""
    p = path or os.environ.get("IWANNA_IWBTGR_PACK") or PACK_PATH
    if not os.path.isfile(p):
        raise FileNotFoundError(
            f"{GAME_ID} pack not found at {p}. Build it locally from a "
            "user-supplied source checkout:\n"
            "  git clone https://github.com/aut0mat1clol/IWBTGR-Autosplitter-mod /tmp/iwbtgr-mod\n"
            "  python -m iwanna_gym.games.iwbtgr_1_5_3 build /tmp/iwbtgr-mod\n"
            "(see iwanna_gym/games/iwbtgr_1_5_3/manifest.json; the official "
            "IWBTGR Source 1.5.3.zip from https://cherry-treehouse.itch.io/"
            "iwbtgr works the same way)")
    with open(p, "rb") as f:
        return f.read()


def build(source_root: str, out_dir: str | None = None,
          write_graph: bool = True) -> dict:
    """Offline: convert the source tree -> IR -> compiled pack (+ graph &
    coverage). Returns a summary dict."""
    import hashlib

    from iwanna_gym.gamepack import compile_pack, save_iwgame, validate
    from .converter import convert

    root = source_root
    sub = os.path.join(source_root, "IWBTGR Source Files")
    if os.path.isdir(sub):
        root = sub
    res = convert(root)
    # exact-behavior layer (milestone: non-boss room completion)
    from tools.importers.iwbtgr.gm82 import load_project
    from . import exact as exact_mod
    proj = load_project(root)
    exact_cov = exact_mod.build_exact(root, proj, res)
    res["coverage"]["exact"] = exact_cov
    out_dir = out_dir or BUILD_DIR
    os.makedirs(out_dir, exist_ok=True)

    rep = validate(res["ir"], allow_unsupported=False)
    if not rep.ok:
        raise RuntimeError("converted IR failed validation:\n" + rep.text())
    save_iwgame(res["ir"], os.path.join(out_dir, GAME_ID + ".iwgame.json"))
    comp = compile_pack(res["ir"])
    pack_path = os.path.join(out_dir, GAME_ID + ".iwpack")
    with open(pack_path, "wb") as f:
        f.write(comp.data)
    with open(os.path.join(out_dir, GAME_ID + ".coverage.json"), "w",
              encoding="utf-8") as f:
        json.dump(res["coverage"], f, indent=1)
    if write_graph:
        with open(GRAPH_PATH, "w", encoding="utf-8") as f:
            json.dump(res["graph"], f, indent=1, sort_keys=False)
            f.write("\n")
    return {
        "rooms": comp.n_rooms,
        "pack_path": pack_path,
        "pack_sha256": hashlib.sha256(comp.data).hexdigest(),
        "pack_bytes": comp.size,
        "coverage": res["coverage"]["totals"],
        "graph_edges": len(res["graph"]["edges"]),
        "source_tree_sha256": res["ir"]["provenance"]["source_checksum_sha256"],
    }
