# iwbtgr_1_5_3_v1 fidelity report

The audit record behind the frozen exact-game pack
(`manifests/iwbtgr_1_5_3_v1.toml`).  Scope: IWBTGR 1.5.3, all 20
gameplay rooms, spawn to completion.  Verdict up front: every gameplay
room audits clean against the source tree, all 24 differential checks
match source-derived expectations, and every known difference is
classified in
[iwbtgr_known_deviations.md](iwbtgr_known_deviations.md) — no
unclassified gameplay approximation is known.  "Exact" throughout this
project means *exact under that deviation table*, never a marketing
shorthand.

## 1. Differential validation

Live lockstep against the original executable is not technically
possible here: the source is a gm82save TEXT export (no compiled
`.exe`/`.gm81` to run), GameMaker 8.2 is Windows-only, and OpenGMK
requires the compiled binary.  Differential validation therefore runs
the engine against **source-derived expected values** — an independent
Python recurrence for the player physics, literal GML constants for
bullets/saves/triggers, geometric predictions for transition and death
frames — plus the pinned deterministic reference traces.

`scripts/differential_validation.py` — **24/24 checks matched**:

| category | checks | result |
|---|---|---|
| player position / velocity / jump state | jump curve (20f held), short-hop (release@4), double jump, terminal vspeed, run distance — engine sequences equal an independent recurrence built only from source constants (jump -8.5, dj -7, grav 0.4, cap 9, run 3, release x0.45) | all match, frame-for-frame |
| bullets | one per press edge; spawn (x, y-2); 16 px/f; 41 moving frames + pre-move destroy on the 42nd (alarm[0]=42); max 4 alive | all match |
| save activation | shoot-activated (source-faithful mode); respawn records the player's position at activation | match |
| room transition frame | free-fall into the rKraidgiefLair boss-door strip: contact frame predicted by the fall recurrence + warp rect | exact frame |
| hazard activation | trigger once-code executes on the contact frame (trigger.gml semantics; alarm[0]=2 is the pulse reset) | match |
| entity positions | 100% provenance join (section 2): every placed instance accounted, per-object emit offsets uniform | match |
| death frame | free fall onto a spikeUp: first frame with round(y)+hb_b >= apex row | exact frame |
| boss state | Birdo phase-2 at 30 cumulative damage; Dracula slot arms at frame 2001 of the intro; full per-fight timelines pinned by the boss test suite + reference traces | match |
| progression flags | the full-game run: 13 waypoints in order, gflags 0x1fe, completions=1, zero deaths, waypoint ticks pinned (`iwbtgr_trace_fullgame.sha`) | match |

## 2. Room-by-room audit

`scripts/audit_iwbtgr_source.py` — **20/20 rooms clean** against an
independent parse of the source tree.  Per room it verifies:
dimensions (source room.txt == pack == runtime), full instance
accounting (every source instance lands in exactly one bucket),
coordinate-offset consistency per object, collision geometry (every
solid-block sample point solid in the pack's tiles ∪ residual rects ∪
entity solids, with source room-start semantics applied — blockFake
destruction, embedded spikes), spike lowering (tile / killer rect /
removable entity), save presence per difficulty, and per-room content
checksums (pinned by `tests/test_iwbtgr_content_checksums.py`).

Buckets: **ent** = produced exact-layer entities (provenance join by
source instance id); **low** = lowered statics (solids, spikes,
killer rects, saves, warps, playerStart, teleporter warps); **cam** =
camera controllers (lowered to the room camera mode); **sld** =
static-solid classes rasterized to geometry; **vis** = visual-only
(no gameplay events).

| room | size | inst | ent | low | cam | sld | vis | saves(M) | source sha | pack sha |
|---|---|---|---|---|---|---|---|---|---|---|
| rGuy1 | 4800x2432 | 1124 | 443 | 528 | 1 | 10 | 142 | 8 | `8ab49ff49c66` | `13c170dae83b` |
| rZelda | 800x1216 | 43 | 7 | 32 | 1 | 1 | 2 | 1 | `02134f3f6e5e` | `0a6ad7688a81` |
| rGraveyard | 4000x1216 | 420 | 126 | 289 | 1 | 0 | 4 | 6 | `390d7f765736` | `c07c5aad1f0d` |
| rMechaBirdoBoss | 800x608 | 11 | 2 | 5 | 0 | 0 | 4 | 0 | `3fef2a4aea93` | `074f1704d702` |
| rKraidgiefLair | 6400x1824 | 680 | 350 | 325 | 1 | 0 | 4 | 5 | `1f08338ebd58` | `bf815c3a6f00` |
| rKraidgiefBoss | 1600x1216 | 248 | 214 | 33 | 1 | 0 | 0 | 0 | `68b3bb0ae812` | `579624a56ae4` |
| rMegaman | 2400x1824 | 485 | 57 | 351 | 1 | 75 | 1 | 5 | `401ba9acb538` | `67b20afb3226` |
| rBowserBoss | 1600x608 | 118 | 55 | 61 | 1 | 0 | 1 | 0 | `03394713cad1` | `bf7cdfff730e` |
| rMetroid | 3200x2432 | 430 | 128 | 291 | 1 | 1 | 9 | 2 | `53e5cb8ad6f0` | `d510200052f6` |
| rFactoryOutskirts | 4800x3648 | 1104 | 315 | 772 | 1 | 0 | 16 | 15 | `e5c47ee48b2b` | `8a0e54042e35` |
| rCastlevania | 1600x1216 | 178 | 33 | 141 | 1 | 0 | 3 | 3 | `d5973e3512e6` | `03918ec4fa20` |
| rDraculaBoss | 800x608 | 45 | 5 | 40 | 0 | 0 | 0 | 0 | `b42f62debbe5` | `1fce3d78c60a` |
| rGuyEntrance | 800x608 | 29 | 6 | 16 | 0 | 0 | 7 | 1 | `d7841f4b727b` | `832b795d3973` |
| rGuyRoad | 30000x608 | 462 | 273 | 126 | 1 | 0 | 62 | 6 | `cecbc51c2d30` | `5073d6614ec6` |
| rGuyFortress1 | 2400x608 | 214 | 152 | 57 | 1 | 0 | 4 | 3 | `06d71a4378d6` | `920255550a99` |
| rGuyLabyrinth | 3200x2432 | 439 | 34 | 404 | 1 | 0 | 0 | 1 | `9b359b58e090` | `42fa804faa53` |
| rGuyFortress2 | 5600x1824 | 741 | 398 | 334 | 1 | 0 | 8 | 6 | `c941ef1265e7` | `3fc5742233e8` |
| rGuyTower | 1600x3040 | 368 | 5 | 360 | 1 | 0 | 2 | 2 | `6abc654d6021` | `4d083e6d78cd` |
| rGuyBoss | 800x1216 | 89 | 52 | 30 | 0 | 0 | 7 | 0 | `9461db4a8085` | `9e49105b4c2b` |
| rEnding | 800x4040 | 109 | 2 | 44 | 0 | 0 | 63 | 0 | `8d75b39b426c` | `a804228a8836` |

Totals: 7,337 placed instances across the gameplay rooms, all
accounted; **39/39 pack warps runtime-walked** to their destinations
(including the eight flag-gated trophy teleporters and the
orb_dracula conditional door, with their activation flags); the
EntranceTele six-orb gate verified in both directions by the test
suite.

Coordinate audit: 175 entity-producing object types; 169 emit at the
exact source coordinates; five carry one fixed origin-normalization
offset each (FireOnce, FireSometimesUpside, GradiusBoss, GradiusBugz,
GradiusDrones — the collision positions the source sprites occupied);
one (BiggusBrickus) fans out into its 2x5 destructible column by
design.

## 3. Object & event coverage

Every source object placed in a gameplay room is classified — the
coverage gates fail the build otherwise (`excluded_boss` is empty
since the full-game milestone):

- 263 distinct objects appear in gameplay rooms; the audit's event
  inventory covers 600 source #define events across them;
- 182 objects produce exact-layer entities (477 events: Create/Step/
  Alarm/Collision behaviors transliterated per the mechanics docs);
- 12 static-solid classes rasterize to collision geometry
  (11 events, all Create-time);
- 69 visual-only objects (112 events, draw/sound/particle) are
  excluded and itemized;
- per-object event narratives live in `iwbtgr_nonboss_mechanics.md`
  and `boss_architecture.md`; the machine inventory is in
  `build/source_reports/iwbtgr_room_audit.json`.

## 4. Classification summary

Full table with rationale: [iwbtgr_known_deviations.md](iwbtgr_known_deviations.md).

- **exact** — the default for all imported content (enforced by the
  gates and audits above);
- **behaviorally equivalent** — E1..E6 (kill-pass ordering, baked
  paths, Metroid latch deadline, solid-over-spike cells, compile-time
  blockFake, trigger pulse);
- **deliberately simplified visual** — V1..V4 (schematic rendering,
  340 visual instances, Deadcula flip, audio);
- **known gameplay approximation** — G1..G4 (RNG stream, death-timing
  compression, orb-flag timing, VicViper vertical mapping);
- **unsupported** — U1..U5 (ErrorTrap mouse, skip/dev keys, Boss
  Rush, meta rooms, on-disk save files).

## 5. Freeze identity

| field | value |
|---|---|
| pack version | `iwbtgr_1_5_3_v1` |
| pack sha256 | `af31958a5b4ab83df95120d423de2758b28b4f0dfcd356371a72280b046f52c1` |
| source tree sha256 | `b7763bcc0cdede07640076f1623893444baa58feefcaca93471eb734382ce73b` |
| source repo commit | `244c3256` (aut0mat1clol/IWBTGR-Autosplitter-mod) |
| importer | `iwanna_gym.games.iwbtgr_1_5_3.converter` v1.1.0 |
| build | byte-reproducible (two clean builds identical) |
| physics profile | `iwannagym_renex` |
| action profile | `standard6x2` (12 actions) |

Performance: [iwbtgr_performance_report.md](iwbtgr_performance_report.md).
Standing enforcement: `tests/test_iwbtgr_content_checksums.py`,
`tests/test_iwbtgr_fullgame.py`, the boss/room/mechanics suites, and
the three pinned traces.
