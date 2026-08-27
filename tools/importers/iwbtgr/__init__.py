"""IWBTGR (I Wanna Be The Guy: Remastered 1.5.3) source importer.

This milestone implements EXTRACTION AND COVERAGE: a generic gm82save
text-tree reader (`gm82.py`), mechanical semantic classification
(`mapping.py`), and the machine-readable source inventory
(`inventory.py`) — see docs/iwbtgr_source_inventory.md.

Conversion to the canonical .iwgame.json IR (making rooms playable) is
the NEXT milestone; `extract()` says so instead of guessing.

The source tree is user-supplied (never committed): either the official
`IWBTGR Source 1.5.3.zip` from https://cherry-treehouse.itch.io/iwbtgr
unpacked, or the autosplitter-mod redistribution
(https://github.com/aut0mat1clol/IWBTGR-Autosplitter-mod,
"IWBTGR Source Files/") — the inventory records which one was used, its
tree hash, and the marker-detected mod delta.
"""
from __future__ import annotations

import os

from .gm82 import is_gm82_project, load_project           # noqa: F401
from .inventory import (                                   # noqa: F401
    build_inventory,
    doc_object_mapping,
    doc_room_inventory,
    doc_source_inventory,
    save_report,
)

NAME = "iwbtgr"
VERSION = "1.0"


def detect(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    # the IWBTGR project file, either at root or one level down
    if os.path.isfile(os.path.join(path, "IWBTGR.gm82")):
        return True
    sub = os.path.join(path, "IWBTGR Source Files")
    return os.path.isfile(os.path.join(sub, "IWBTGR.gm82"))


def resolve_root(path: str) -> str:
    sub = os.path.join(path, "IWBTGR Source Files")
    return sub if os.path.isdir(sub) else path


def extract(path: str, game_id: str | None = None):
    raise NotImplementedError(
        "iwbtgr conversion to the canonical IR is the next milestone; this "
        "milestone ships the source inventory — run "
        "`python -m tools.iwimport inventory <source>` "
        "(docs/iwbtgr_source_inventory.md)."
    )
