# K2 WARPED static-world coverage (k2warped_gms14)

Static milestone import of **I Wanna Kill the Kamilia 2 WARPED** by
SUDALV92 (his released GMS 1.4 project, git `a6d6dce1`, written blanket
code permission; always labeled K2 WARPED, never Kamilia 2).  Adapter:
`gmx2pack 1.0.0` (`iwanna_gym/games/k2warped_gms14/converter.py`) —
source format -> game-specific adapter -> common IWannaGym IR -> pack.
Source coordinates and parameters preserved; no room designed or
substituted; source tree never committed (users build from their own
clone at the pinned commit).

## Inventory

- **Rooms: 148**, imported in exact source project order (9 unreferenced
  orphan room files excluded and listed below).  36 boss/avoidance
  rooms tagged; meta rooms: rInit, rOptions, rSaveBroken, rTemplate, rTitle.
- **Instances: 19,574** — all accounted with per-instance
  provenance (source room, instance id, object): 12,505 lowered
  statically (`exact`), 7,069 inventoried as
  **unsupported dynamic** for later milestones.  Full inventory:
  `build/source_reports/k2warped_gms14.instances.json` (deterministic
  build artifact, sha pinned in the committed room graph).
- **Room graph:** 108 lowered warp edges (objRoomChanger family:
  `roomTo` creation codes, target_start vs absolute destination modes,
  dormant `enabled=false` warps kept inactive) + 0 scripted
  `room_goto` edges recorded unlowered; 0 unresolved warps.
- **Saves:** objSave instances lowered as checkpoints (bbox-exact);
  variants (objEvilsave, objGiantSave, …) inventoried as dynamic.
- **Starts:** objPlayerStart per room, player created at its exact
  (x, y) as in the source room-start event.
- **Event/code inventory:** 1408 objects with 3928 source events
  (44,617 GML lines) + 227 scripts
  (5,863 lines) catalogued in the coverage JSON.
- **Progression gates:** 21
  `stageUnlocked[...]` writes and
  9 `tempTrigger[...]`
  writes inventoried (implemented in the dynamics milestone).

## Object classification (behavioral, from the object XML)

{ "decor_no_events": 92, "dynamic": 1276, "killer_static": 26, "player": 1, "save": 6, "solid_static": 50, "spike_static": 12, "start": 1, "warp": 4 }

Static lowering covers: solid blocks (tile grid + non-aligned solid
rects, GM bbox math incl. the 16px-grid rooms), spikes (tile triangles
or shaped killer rects; reskins and the room-conditional invisible
spikes included), other motionless killer-chained hazards (bbox rects),
saves, warps, player starts.

### Justified static overrides

Objects whose extra source events were verified harmless-to-static by
direct code inspection (recorded in `static_overrides` in the coverage
JSON): the canonical objBlock/objSpike* family (visual-only create
code; the GradiusLaser interaction is commented out for spikes and
deferred as a pending Boss6 semantic for blocks), objIntroBlock,
obj6B/6C/6DBlock (Giantkid destructibility pending), objCQBlockB/C.

## Unsupported dynamic mechanics (top by placed instances)

| object | instances | events |
|---|---|---|
| objBlockFake | 1111 | create, collision, draw |
| objBoss6BSoftBlock | 844 | create, alarm, alarm, collision |
| objBlockInvis | 559 | create, step |
| objBlock1CHM | 319 | create, alarm |
| objLastBlock | 310 | create, step |
| objFreeTrigger | 291 | create, collision, other |
| objS5SpikeUp | 224 | create, step |
| objMovingPlatform | 132 | create, step |
| objS5SpikeDown | 110 | create, step |
| oRedLightLine | 79 | create, draw |
| objS5Switcher | 63 | create, alarm, collision, draw |
| objS5SpikeLeft | 56 | create, step |
| objGeezerZeldaWater | 55 | create |
| objFgetrap1 | 54 | create, destroy, step, other |
| objCherry | 51 | create, other |

Plus the avoidance/boss actor families (oRed* Red-Lunar-Abyss customs,
objBoss*, bullet spawners), moving platforms/spikes, triggers and trap
launchers, water regions (objGeezerZeldaWater, objDiearyWater — physics
regions), gravity-flip and dotkid/giant-kid modifiers, cameras
(objSmoothCamera), fake/invisible blocks, and every menu/UI object.
None of these is approximated: rooms containing them are importable and
walkable on their static geometry, and each such instance is explicitly
`unsupported` in the inventory until its milestone.

## Orphan room files (in the tree, not referenced by the project)

rAchievements, rDifficultySelect, rExtraBoss, rExtraExp, rExtraSymetry, rMenu, rSampleRoom, rStage4KTGC, rTitleEngine

## Validation

`tests/test_k2w_static.py`: source room order preserved (148), per-room
dimensions vs an independent source parse, instance counts vs source,
all transition targets exist, every enabled warp resolved at runtime
(including the in-room repositioning warp), save positions vs source,
graph re-derivation equality, source checksum stamped in the pack
provenance, dynamic inventory completeness, env API for both modes
(`IWannaEnv(game="k2warped_gms14", mode="full_game"/"room")`), and
deterministic replay.
