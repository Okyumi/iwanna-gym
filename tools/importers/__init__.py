"""Source-specific extractors: source project -> canonical IR.

Each importer module exposes:

    NAME: str                       # registry key
    detect(path) -> bool            # does this importer recognize the source?
    extract(path, game_id=None) -> dict   # IR document (schema.new_gamepack)

Importers run OFFLINE only. They must never guess: source content they
cannot identify is emitted with mapping_status="unknown"; content they can
identify but the runtime cannot represent is "unsupported" (with notes).
"""
from __future__ import annotations

from . import synthetic
from . import gm82
from . import iwbtgr

_IMPORTERS = {m.NAME: m for m in (synthetic, gm82, iwbtgr)}


def get_importer(name: str):
    if name not in _IMPORTERS:
        raise KeyError(f"no importer {name!r}; available: {sorted(_IMPORTERS)}")
    return _IMPORTERS[name]


def detect_importer(path: str):
    """Return the first importer whose detect() accepts the path, or None."""
    for mod in _IMPORTERS.values():
        try:
            if mod.detect(path):
                return mod
        except Exception:
            continue
    return None


def available() -> list[str]:
    return sorted(_IMPORTERS)
