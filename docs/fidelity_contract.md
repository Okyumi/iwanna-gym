# Exactness (fidelity) contract

This document defines what "exact" means when iwanna-gym imports complete games
designed by existing I-Wanna creators. It exists so that no part of the project
ever claims more exactness than it can demonstrate, and so that the original
2007 *I Wanna Be The Guy* is never silently conflated with *I Wanna Be The Guy:
Remastered* or with generic fangame-engine physics.

Fidelity is split into four independent axes — **content**, **physics**,
**visual**, and **runtime** — each with its own definition of "exact" and its
own verification obligations. A game import may be exact on one axis and
explicitly non-exact on another; the documentation for each imported game must
state its status per axis.

---

## 1. Game identifiers

Exact-game targets are named by explicit identifiers. An identifier binds a
specific content set to a specific physics profile; the two never mix
implicitly.

| identifier | game | engine of record | physics profile |
|---|---|---|---|
| `iwbtg_original_2007` | I Wanna Be The Guy (Kayin, 2007–2008; final public builds are the two 2008-01-31 "beta" .mfa snapshots, `(fs)` and `(slomo)`) | Multimedia Fusion 2 | `physics.iwbtg_original_2007` |
| `iwbtgr_1_5_3` | I Wanna Be The Guy: Remastered v1.5.3 (Cherry Treehouse / Natsu, Renko, renex, Floogle; endorsed by Kayin) | GameMaker 8.2 (GM 8.1.141 + GM8.2 patch), Yuuutu engine, prepatched with gm8x_fix | `physics.yuuutu_gm8` |
| `iwannagym_research_v1` | the existing controlled/procedural research rooms in this repository (named levels, 20 trap rooms, procedural needle generator) | native C core | `physics.iwannagym_renex` |

Rules:

- The original game and Remastered are **different games** for the purposes of
  this benchmark: different engine, different physics, partially different
  content and save/difficulty semantics. Documentation, environment ids, level
  packs, and result tables must always carry one of the identifiers above.
- The word "IWBTG" without an identifier is only allowed when a statement is
  true of both versions.
- The existing research rooms (`iwannagym_research_v1`) are a **separate
  benchmark family**. They are original content in fangame style; they are not
  content-exact to any shipped game and must never be presented as such.
- New game imports get new identifiers of the same shape
  (e.g. `k2warped_gms14`, `iwktk3_1_30`), pinned to an exact version and
  recorded in `third_party/source_manifest.toml`.

---

## 2. Content fidelity

Content fidelity means the imported game pack reproduces, from the source
project of record, all gameplay-relevant content:

- room dimensions and per-room coordinate systems;
- room coordinates / positions of rooms in the world and the room graph;
- solid geometry (blocks, platforms, slopes if present, jump-through solids);
- hazards (spikes, killers, moving hazards) with their gameplay-relevant
  extents;
- object instance positions (every placed instance, at its authored x/y);
- object parameters (creation code values, instance-specific settings,
  scale/rotation where the source format records them);
- trigger regions and trigger timing (frame counts, alarm values, activation
  conditions);
- save locations, and **difficulty-specific save availability** (Medium /
  Hard / Very Hard / Impossible in IWBTG remove or keep specific saves — the
  difficulty flag of every save must be imported, not approximated);
- room transitions and their edge/warp semantics;
- warps (source, destination, conditions);
- progression flags (items collected, bosses defeated, unlocked routes);
- route structure (which rooms are reachable from which, in what order the
  game intends);
- boss states and attack patterns (state machines, HP, per-state spawn
  patterns, timings);
- completion conditions (what constitutes beating a boss, a route, the game).

A game may be labeled **content-exact** only when every item above is either
(a) extracted mechanically from the identified source project by a committed
importer, or (b) explicitly listed in that game's known-deviations table.
An empty deviations table plus a mechanical importer is the goal; a deviations
table is the honest fallback; silence is not allowed. Manual redesign of
content ("re-drawing rooms by eye") is prohibited for exact-game packs.

Verification obligation: per-room instance counts, instance coordinate
checksums, and the room graph extracted by the importer must be committed as
fixtures and covered by tests, so content drift is detectable without
redistributing the source.

## 3. Physics fidelity

Physics profiles are named and kept distinct. Matching one profile is never
evidence of matching another.

### `physics.iwannagym_renex` — what the current C core implements

The current engine (`c_src/iwanna.h`) is a line-by-line port of the
renex/renex² GM8.2 engine's player physics: 50 Hz frame loop, run speed
3 px/frame, jump −8.5, double jump −7, gravity 0.4, vertical speed cap 9,
release-to-short-hop ×0.45, 11×20 px player hitbox, GameMaker banker's
rounding, pixel-stepped solid collision. `tests/test_physics.py` asserts the
analytic consequences (86.1 px full jump, 57.8 px double jump, 9.4 px/frame
max applied fall).

### `physics.yuuutu_gm8` — Yuuutu-family fangame physics (IWBTGR, most classics)

The Yuuutu engine and its descendants (renex, renex², Zephyr, Guy Remastered)
share the constants above; we have verified them directly in the GML source of
renex² (`source/objects/Player.gml`, `source/scripts/player_capjump.gml`,
`global.game_speed = 50`) and of the Zephyr GM8.2 engine
(`objects/objPlayer.gml`, `scripts/scrPlayerVJump.gml`, `room_speed = 50`).
IWBTG: Remastered is built on the Yuuutu engine in GM8.2, so
`physics.yuuutu_gm8` is its physics profile of record.

Status: **believed identical to `physics.iwannagym_renex` in the player
movement constants, but not yet verified against the actual IWBTGR 1.5.3
source package.** Until the importer work diffs the IWBTGR player object
against the C core (including collision-mask details, water/vine/platform
edge cases, and any IWBTGR-specific tweaks), documentation may say "Yuuutu
engine constants, verified against renex²/Zephyr" — it may **not** say
"verified against IWBTGR 1.5.3".

### `physics.iwbtg_original_2007` — the original MMF2 game

The original game is a Multimedia Fusion 2 game and does **not** use
GameMaker/Yuuutu physics. Community-documented differences (Delicious-Fruit
reviews of the original; Kayin's own Remastered announcement, which describes
moving the game "to Yuuutu fangame physics"):

- only two jump heights — there is no variable-height release (no ×0.45
  mechanic); fangame engines by contrast allow near-continuous jump heights;
- known input jank (occasional unintended double jumps) and frame-pacing
  problems severe enough that two separate builds, `(fs)` and `(slomo)`, were
  shipped.

**No numeric movement constants for the original game are currently known to
this project.** None are published in any community source we located
(speedrun.com/iwbtg has no guides). The only authoritative source is the
released `.mfa` project itself, from which the values must be extracted before
any claim is made. Until then:

- nothing in this repository may be called "exact original IWBTG physics";
- `physics.iwbtg_original_2007` exists in name only, with status
  **unimplemented / values unextracted**;
- an `iwbtg_original_2007` content import running on Yuuutu-style physics
  must be labeled exactly that (original content, non-original physics), the
  same way IWBTG: Remastered itself is labeled.

### Profile rules

- Every imported game pack declares its physics profile.
- A profile claim of the form "exact X physics" requires a committed,
  test-backed extraction from X's engine source (as was done for renex²), not
  family resemblance.
- Differences discovered between a family profile and a specific game's
  engine become either a new profile or a documented per-game deviation.

## 4. Visual fidelity

Visual reproduction is **not** part of the research contribution and is not
required for any fidelity level. The lightweight numpy renderer may remain
schematic (rects, tile colors). "Exact-game" in this project means exact
gameplay content and semantics, not pixels. The only visual obligations are
gameplay-relevant ones, and they belong to content/runtime fidelity anyway:
collision masks, hitbox extents, and trigger regions must match the source
even when their on-screen appearance does not.

If a future renderer reproduces original art, that art follows the
third-party asset rules in `third_party/SOURCES.md` (no redistribution
without a clear license; assets flow through the user-provided-files importer
path).

## 5. Runtime fidelity

Runtime fidelity is about the simulation loop, independent of which rooms are
loaded:

- **Determinism**: identical initial state + identical action sequence ⇒
  bit-identical trajectories. This is already asserted for the current engine
  (`tests/test_entities.py`, `tests/test_events.py` deterministic-replay
  tests) and remains mandatory for imported games. Any source-game
  randomness must be reproduced through the environment's seeded RNG and
  documented per game.
- **Source-faithful object state transitions**: imported objects (bosses,
  traps, platforms) step through the same state machines with the same frame
  timings as the source project's event/GML code, as extracted by the
  importer.
- **Source-faithful reset and checkpoint semantics**: death → respawn at the
  last activated save with the source game's restored state (position,
  djump, room state, progression flags), including what the source game does
  and does not reset on death; difficulty-dependent save rules follow content
  fidelity.
- **Source-faithful collision masks where they affect gameplay**: the player
  hitbox and hazard masks (e.g. triangular spike masks, per-sprite precise
  masks in GM8) must match the source's gameplay behavior. Purely cosmetic
  mask details with no reachable gameplay consequence may be simplified, but
  any such simplification is a documented deviation.

Frame-rate semantics are part of runtime fidelity: Yuuutu-family games run a
50 Hz logic loop (already matched); `iwbtg_original_2007` frame pacing under
MMF2 was irregular by construction and its runtime profile must be defined at
extraction time rather than assumed to be a clean fixed-rate loop.

---

## 6. Claims discipline

- Every fidelity claim in READMEs, docs, or papers must be traceable to a
  test, a committed importer, or a cited source inspection — otherwise it is
  not made.
- Current honest summary (2026-08-27): the repository is **runtime-exact and
  physics-exact to the renex² GM8.2 engine** (verified constants, analytic
  tests), **content-original** (research rooms; six levels are homages, not
  reproductions), and contains **no exact-game content yet**. The recommended
  first exact-game target is `iwbtgr_1_5_3` — see
  `docs/exact_game_source_audit.md`.
