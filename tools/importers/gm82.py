"""GameMaker 8.2 text-tree importer — SCAFFOLD ONLY.

Target source: gm82save per-resource text projects (the format renex² is
stored in, and possibly the IWBTGR 1.5.3 source package — its internal
layout is still unverified; see docs/exact_game_source_audit.md and
third_party/source_manifest.toml).

Deliberately unimplemented in this milestone: the generic pipeline lands
first with the synthetic fixture; full-game extraction is the next
milestone. This stub exists so the CLI reports a clear, honest error
instead of pretending GM projects are importable today.
"""
from __future__ import annotations

import os

NAME = "gm82"
VERSION = "0.0-scaffold"


def detect(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    return any(fn.endswith(".gm82") for fn in os.listdir(path))


def extract(path: str, game_id: str | None = None):
    raise NotImplementedError(
        "the gm82 importer is a scaffold: GM8.2 text-tree extraction is the "
        "next milestone (docs/importer_architecture.md, 'Adding an importer'). "
        "Nothing is guessed in the meantime."
    )
