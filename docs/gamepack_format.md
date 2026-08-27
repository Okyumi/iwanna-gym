# Game-pack formats: `.iwgame.json` (canonical IR) and `.iwpack` (runtime)

Two representations, one strict division of labor
(docs/importer_architecture.md has the pipeline around them):

* **`.iwgame.json`** — the inspectable canonical intermediate
  representation: human-readable JSON, diffable, carries full provenance
  and mapping statuses. Everything auditable lives here.
* **`.iwpack`** — the compact runtime representation compiled from the IR:
  little-endian binary with contiguous arrays, fixed-width records,
  stable numeric IDs and precomputed offsets. The C runtime decodes it
  once at environment construction; **no per-frame string lookup, no
  per-frame parsing, no allocation during stepping**.

## Canonical IR (`.iwgame.json`, format `iwgame/1`)

Top-level structure (all sections always present; empty lists where the
game has none):

```jsonc
{
  "format": "iwgame/1",
  "metadata":   {"game_id", "title", "notes"},
  "provenance": {"source_game", "source_version", "source_format",
                 "source_checksum_sha256", "importer", "importer_version"},
  "physics_profile": "iwannagym_renex",   // must be an IMPLEMENTED profile
  "action_profile":  "standard6",
  "global_flags": [{"id": 1, "name": "door_unlocked", "provenance": {...}}],
  "object_definitions": [ ... ],
  "rooms": [ ... ],
  "room_graph": {"start_room": 0, "edges": [[0, 1, "warp"], [1, 0, "edge_left"]]},
  "difficulty_variants": [ ... ],   // parsed; runtime support pending
  "bosses": [ ... ],                // beyond boss_radial8 instances: unsupported
  "completion": {"type": "reach_goal", "room": 1}
}
```

### Mapping status and provenance (every element)

Each object definition, instance, event, difficulty variant, and boss
carries:

* `mapping_status`: `exact` | `equivalent` | `unsupported` | `unknown`
  * `exact` — reproduced with identical semantics;
  * `equivalent` — reproduced with a documented behavioral difference
    (the `notes` field must say what differs);
  * `unsupported` — identified in the source, but the runtime cannot
    represent it;
  * `unknown` — the importer could not identify it. Importers never
    guess.
* `provenance`: `source_game`, `source_version`, `source_room`,
  `source_object`, `source_instance`, `source_event` (whichever apply).

Validation fails on any `unsupported`/`unknown` element unless
`--allow-unsupported` (inspection mode) is passed; compiling with
`--allow-unsupported` drops them **visibly** — they are listed in the
pack metadata under `dropped` and the pack is marked `incomplete`.

### Rooms

```jsonc
{
  "id": 0, "name": "rmA",
  "width_tiles": 20, "height_tiles": 12,
  "tiles": ["####...", ...],   // canonical layer: # ^ v < > G . (S = start)
  "start": {"x": 80, "y": 343},        // player origin, px (overrides 'S')
  "goal":  {"x": 432, "y": 336},       // null => room has no terminal goal
  "instances": [
    {"object": "sMovingPlatform", "x": 432, "y": 240,
     "tag": 0, "params": {"vx": 1, "range": 32},
     "mapping_status": "equivalent", "notes": "...", "provenance": {...}}
  ],
  "events": [
    {"when": "enter_region", "x0": 320, "y0": 0, "x1": 352, "y1": 384,
     "once": true, "actions": [{"do": "set_flag", "id": 1}],
     "mapping_status": "exact", "provenance": {...}}
  ],
  "checkpoints": [{"x": 176, "y": 336, "tag": 7}],   // sugar for save instances
  "warps": [{"x": 560, "y": 336, "dest_room": 1, "dest_x": 80, "dest_y": 343}],
  "edges": {"left": null, "right": 1, "up": null, "down": null}
}
```

Coordinates are room pixels (32 px tiles); entity positions are centers,
matching the runtime. Event conditions/actions use the same vocabulary as
the engine's declarative event system (README "Trigger/event system"),
plus `flag_set` / `set_flag` / `clear_flag` for global progression flags.

Canonical entity kinds (→ runtime `E_*`): `platform`, `spikeball`,
`trigger_zone`, `trap`, `projectile`, `shooter`, `enemy`, `save`, `warp`,
`boss_radial8`, `gate`; tile kinds `tile_block`, `tile_spike_*`,
`tile_goal`; and `player_start`. Collision masks are per-kind:
`rect` or `spike_triangle` (the two the runtime implements; anything else
must be `unsupported`).

## Runtime pack (`.iwpack`, version 1)

Authoritative layout: `c_src/gamepack/iwpack.h` (C) and
`iwanna_gym/gamepack/compilepack.py` (writer). Summary:

```
IWPackHeader   64 B   magic "IWPK", version, total_size, n_rooms,
                      start_room, n_flags, physics_profile, action_profile,
                      max_tiles/max_spawns/max_events/max_actions,
                      rooms_off, meta_off, meta_len
per room:             uint8 tile grid  (tw*th, 4-byte padded)
                      IWPackEnt[n_spawns]    72 B fixed records
                      IWPackEvt[n_events]    56 B fixed records
                      IWPackAct[n_actions]   32 B fixed records
IWPackRoomRec[n_rooms] 72 B each: dims, start, goal|objective, has_goal,
                      edge links (L/R/U/D room ids), section offsets/counts
metadata blob         UTF-8 JSON: metadata, provenance, global flags,
                      per-element provenance index, dropped list,
                      incomplete marker
```

Properties the compiler guarantees and the loader re-validates:

* every offset/count in bounds; event action-slices inside the room's
  action pool; edge links valid room ids;
* `physics_profile` / `action_profile` are ones this runtime implements —
  a pack compiled for a different profile is REJECTED at load, never
  approximated;
* per-pack maxima in the header let the runtime allocate its live buffers
  exactly once at construction.

The metadata blob is never read during stepping (or by the loader at
all); inspection tools read it, and it is how source provenance survives
into the shipped artifact.

## Runtime semantics (pack mode)

* The env allocates live buffers from the header maxima at construction;
  entering a room is a bounded `memcpy` of that room's sections — no
  allocation, no parsing, mid-episode or at reset.
* **Room transitions**: warp entities may carry a destination room;
  linked room edges transition with velocity preserved, entering at the
  opposite edge. Rooms reset on entry (GM8 fangame semantics).
* **Persist across transitions**: global flags, the active save point
  (which may be in another room — death in checkpoint mode respawns
  there), the episode tick, and the RNG stream.
* **Reset on entry**: room entities, room events (including
  `room_enter`), gate stamping.
* **Episode reset** returns to the start room and clears flags, save, and
  transition count.
* Rooms without a goal never terminate the episode; their `goal_x/y` is a
  shaping objective only (the compiler points it at the room's exit).
* Determinism: identical seed + action sequence ⇒ bit-identical
  trajectories, asserted in `tests/test_gamepack.py`.

## Versioning

`IWPACK_VERSION` is bumped on any layout change; the loader rejects
other versions (no silent migration). The IR `format` field works the
same way. Packs are build artifacts: regenerate from the IR rather than
migrating binaries.
