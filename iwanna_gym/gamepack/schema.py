"""Canonical intermediate representation (IR) for complete games.

The IR is a plain JSON document (conventional extension: ``.iwgame.json``)
designed to be read by humans and diff tools; the compiler
(:mod:`iwanna_gym.gamepack.compilepack`) turns it into the compact binary
``.iwpack`` consumed by the C runtime. Field-by-field documentation lives
in docs/gamepack_format.md.

Every imported element carries:

* ``mapping_status`` — one of ``exact`` / ``equivalent`` / ``unsupported``
  / ``unknown`` (see MAPPING_STATUSES below). The importer must never
  guess: anything it cannot identify is ``unknown``; anything it can
  identify but the runtime cannot represent is ``unsupported``; anything
  represented with a documented behavioral difference is ``equivalent``.
* ``provenance`` — where the element came from
  (source_game / source_version / source_room / source_object /
  source_instance / source_event, plus importer name+version at the top
  level). Provenance is embedded verbatim in the compiled pack's metadata
  blob, so it survives conversion end to end.
"""
from __future__ import annotations

import copy
import json
from typing import Any

FORMAT_VERSION = "iwgame/1"

#: how faithfully an element was mapped from its source
MAPPING_STATUSES = ("exact", "equivalent", "unsupported", "unknown")

#: named physics profiles -> numeric id in the binary pack header.
#: Only profiles actually implemented by a runtime may appear here; see
#: docs/fidelity_contract.md before adding one.
PHYSICS_PROFILES = {"iwannagym_renex": 0}

#: named action profiles -> numeric id
ACTION_PROFILES = {"standard6": 0}

# ---- runtime enums (MUST mirror c_src/iwanna.h) ----

ENTITY_KINDS = {
    # kind -> runtime E_* id
    "platform": 1,
    "spikeball": 2,
    "trigger_zone": 3,
    "trap": 4,
    "projectile": 5,
    "shooter": 6,
    "enemy": 7,
    "save": 8,
    "warp": 9,
    "boss_radial8": 10,
    "gate": 11,
}

EVENT_WHEN = {
    "room_enter": 0,
    "enter_region": 1,
    "leave_region": 2,
    "touch_object": 3,
    "land_on_object": 4,
    "pass_x": 5,
    "pass_y": 6,
    "timer": 7,
    "object_destroyed": 8,
    "save_activated": 9,
    "flag_set": 10,
}

EVENT_ACTIONS = {
    "activate": 0,
    "deactivate": 1,
    "launch": 2,
    "set_gravity": 3,
    "move": 4,
    "teleport": 5,
    "spawn": 6,
    "destroy": 7,
    "make_killer": 8,
    "make_harmless": 9,
    "make_solid": 10,
    "make_unsolid": 11,
    "open_gate": 12,
    "close_gate": 13,
    "start_timer": 14,
    "set_dir": 15,
    "set_flag": 16,
    "clear_flag": 17,
}

#: entity flag bits (mirror iwanna.h)
EF_ACTIVE, EF_DEADLY, EF_SOLID_TOP, EF_DORMANT = 1, 2, 4, 8
CM_PLAYER = 1

#: canonical tile characters (same vocabulary as the classic text levels)
TILE_CHARS = {
    ".": 0, " ": 0,
    "#": 1,
    "^": 2, "v": 3, "<": 4, ">": 5,
    "G": 6,
    "S": 0,   # start marker: position, not a tile
}

TILE_PX = 32


def new_gamepack(game_id: str, *, title: str = "", source_game: str = "",
                 source_version: str = "", source_format: str = "",
                 importer: str = "", importer_version: str = "") -> dict[str, Any]:
    """A fresh, empty IR document with every top-level section present."""
    return {
        "format": FORMAT_VERSION,
        "metadata": {
            "game_id": game_id,
            "title": title,
            "notes": "",
        },
        "provenance": {
            "source_game": source_game,
            "source_version": source_version,
            "source_format": source_format,
            "source_checksum_sha256": "",
            "importer": importer,
            "importer_version": importer_version,
        },
        "physics_profile": "iwannagym_renex",
        "action_profile": "standard6",
        "global_flags": [],          # [{"id", "name", "provenance"}]
        "object_definitions": [],    # [{"name", "kind", "collision_mask",
                                     #   "mapping_status", "notes", "provenance"}]
        "rooms": [],                 # see docs/gamepack_format.md
        "room_graph": {"start_room": 0, "edges": []},
        "difficulty_variants": [],   # parsed-but-unsupported at runtime for now
        "bosses": [],                # beyond boss_radial8 instances: unsupported
        "completion": {"type": "reach_goal"},
    }


def new_room(room_id: int, name: str, width_tiles: int, height_tiles: int) -> dict[str, Any]:
    return {
        "id": room_id,
        "name": name,
        "width_tiles": width_tiles,
        "height_tiles": height_tiles,
        "tiles": ["." * width_tiles for _ in range(height_tiles)],
        "start": None,               # {"x": px, "y": px} (player origin)
        "goal": None,                # {"x": px, "y": px}; None = no terminal goal
        "instances": [],             # [{"object", "x", "y", "params", "tag",
                                     #   "mapping_status", "provenance"}]
        "events": [],                # [{"when", ...keys, "actions": [...],
                                     #   "mapping_status", "provenance"}]
        "checkpoints": [],           # sugar over save instances
        "warps": [],                 # [{"x","y","dest_room","dest_x","dest_y",...}]
        "edges": {"left": None, "right": None, "up": None, "down": None},
    }


def load_iwgame(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("format") != FORMAT_VERSION:
        raise ValueError(
            f"{path}: unsupported IR format {doc.get('format')!r} "
            f"(expected {FORMAT_VERSION})"
        )
    return doc


def save_iwgame(doc: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
        f.write("\n")


def iter_elements(doc: dict[str, Any]):
    """Yield (where, element) for every status-carrying element in the IR."""
    for od in doc.get("object_definitions", []):
        yield f"object_definitions/{od.get('name')}", od
    for room in doc.get("rooms", []):
        rn = room.get("name", room.get("id"))
        for i, inst in enumerate(room.get("instances", [])):
            yield f"rooms/{rn}/instances[{i}]({inst.get('object')})", inst
        for i, ev in enumerate(room.get("events", [])):
            yield f"rooms/{rn}/events[{i}]({ev.get('when')})", ev
    for i, dv in enumerate(doc.get("difficulty_variants", [])):
        yield f"difficulty_variants[{i}]", dv
    for i, b in enumerate(doc.get("bosses", [])):
        yield f"bosses[{i}]", b


def deep_copy(doc: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(doc)
