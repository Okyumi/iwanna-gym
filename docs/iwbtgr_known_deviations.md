# iwbtgr_1_5_3_v1 — known deviations

The complete, classified list of every known difference between the
frozen `iwbtgr_1_5_3_v1` pack and IWBTGR 1.5.3 as exported from source
(tree `b7763bcc…`, see `manifests/iwbtgr_1_5_3_v1.toml`).  Labels
follow the fidelity vocabulary:

- **exact** — transliterated behavior; no known difference.  This is
  the default for everything NOT listed below: the coverage gates fail
  the build if a placed gameplay instance is unaccounted, and the room
  audit + differential validation scripts verify the claim per room
  and per mechanic.
- **behaviorally equivalent** — implementation differs, outcomes
  provably identical for every reachable state.
- **deliberately simplified visual behavior** — presentation only;
  gameplay state untouched.
- **known gameplay approximation** — CAN alter moment-to-moment
  gameplay relative to the source; bounded and documented.
- **unsupported** — source feature deliberately absent.

"Exact" in this project's docs always means "exact under this table";
an environment with unreported gameplay approximations would not
qualify.  The per-item tests column names the enforcement.

## Known gameplay approximations

| id | area | source behavior | engine behavior | bound / enforcement |
|---|---|---|---|---|
| G1 | RNG stream | one global GM8 RNG sequence shared by every object | env-seeded RNG at the same call sites with the same distributions (`random(n)`, `choose(…)`, `irandom(n)`) | attack-pattern *sequences* differ from any particular source playthrough; distributions, spawn sites, and timings match. Required for seeded benchmark determinism. Enforced by determinism tests + pinned traces |
| G2 | death & cutscene timing | kill → gameOver object → fade/music (~1 s) before retry; Kraidgief's SPD grab plays a ~570-frame piledriver before the kill | death registers on the same frame; respawn is immediate on the next step; the grab kills at grab-close | deaths, attempt counters, and restored state are source-faithful; only dead time is removed. `tests/test_save_semantics.py`, boss tests |
| G3 | orb flag timing (Dracula, Mother) | `global.orb_on_room_change` applies the orb flag + save at the *next room change* | flag + checkpoint land at pickup (uniform for all orbs); OrbDracula's 185-frame Alarm_0 exit warp itself is exact | visible only if the player dies between pickup and the room change — a degenerate window the source itself handles murkily (the pending alarm dies with the room). `tests/test_iwbtgr_fullgame.py::test_dracula_segment_and_orb_warp` |
| G4 | VicViper vertical input | flight reads a dedicated up/down axis (`global.input_v`) | jump held = up 4 px/f, otherwise down 4 px/f (no up/down axis in the 12-action space) | hovering at constant height is impossible (the source could); speeds, autofire cap, hazards, and the victory sequence are exact. `tests/test_iwbtgr_fullgame.py::test_viper_segment_victory_sweep` |

## Behaviorally equivalent

| id | area | difference | why equivalent |
|---|---|---|---|
| E1 | kill-check ordering | GM interleaves step events → motion → collision events; the engine runs motion then one combined kill pass in the same frame | frame-identical outcomes for every reachable case (verified when the pass was introduced; regression-guarded by the per-room determinism tests and pinned traces) |
| E2 | GM path motion | runtime path evaluation replaced by offline sampling at GM's precision-4 corner-cutting with per-point speeds, baked into the pack keys pool | sampled trajectories reproduce the runtime evaluator; no per-step source interpretation. Boss fights using paths replay frame-identically (traces) |
| E3 | Metroid latch | source drains health while attached; the env has no health meter | the source drain is lethal in exactly 100 contact frames with no escape; the engine kills after the same 100 frames |
| E4 | solid-over-spike tiles | source stacks a solid block over a spike in the same cell (rGuy1, rFactoryOutskirts); the tile grid stores one code and the solid wins | the embedded spike is unreachable in the source too — the solid's rectangle fully covers it (room audit: every such cell verified) |
| E5 | blockFake room-start destruction | `blockFake.Other_4` destroys every overlapping real block at room start | applied at compile time: the pack simply never contains those solids (room audit verifies the source semantics produce the pack geometry) |
| E6 | trigger pulse | trigger "o" once-code runs on the touch frame; `alarm[0]=2` then clears the trigger's pulse flag | same-frame op execution and a 2-frame pulse in the engine; measured in `scripts/differential_validation.py` (hazard activation) |

Also equivalent: vestigial source code with no readers is dropped
(e.g. `MechaHitbox3.wait`), and origin-normalization offsets on five
spawned classes (FireOnce, FireSometimesUpside, Gradius{Boss,Bugz,
Drones}) place entities at the same collision positions the source
sprites occupied (room audit: offset consistency check).

## Deliberately simplified visual behavior

| id | area | note |
|---|---|---|
| V1 | rendering | the environment renders schematically (collision masks, not source sprites/backgrounds/tile art); destroyed scenery keeps its static tile art in the schematic layer (e.g. Kraidgief ceiling). Visual fidelity is explicitly not claimed |
| V2 | visual-only instances | 340 placed instances with no gameplay events are excluded and itemized in the coverage report (decorations, particles, the Samus escape cameo, the rEnding tableau, intro stars, etc.) |
| V3 | Deadcula true-form flip | the source flips `image_xscale` by facing during the reveal; the collision mask swaps in unflipped (facing kept for the death animation) |
| V4 | audio | `play_sound` / `play_music` calls are dropped; where audio gates gameplay timing (e.g. intro beats) the frame counts are kept |

## Unsupported

| id | area | note |
|---|---|---|
| U1 | ErrorTrap mouse dialog | the fake GM error dialog needs mouse input (outside the action space); the trap fires and auto-dismisses after the source delay |
| U2 | skip & dev keys | `skipButton()` intro skips and debug damage keys are unmapped (outside the action space / dev-gated) |
| U3 | Boss Rush | `rBossRush` and the `defeat_bossrush` hooks are out of scope (meta-mode) |
| U4 | meta rooms | rInit, rTitle, rFiles, rDev, rCredits, rUnlocks are not gameplay and are not imported as playable content (difficulty is an env parameter instead of the menu flow, gating difficulty-specific saves exactly as the source does) |
| U5 | on-disk save files | the source persists per-slot save files across sessions; the environment keeps run state (checkpoint, flags, attempts) in memory per instance |

## Change control

Any new difference found later must be added here with a label before
release, and the freeze re-recorded (`manifests/iwbtgr_1_5_3_v1.toml`)
if pack content changed.  The room audit
(`scripts/audit_iwbtgr_source.py`), the differential validation
(`scripts/differential_validation.py`), and the content-checksum tests
(`tests/test_iwbtgr_content_checksums.py`) are the standing
enforcement.
