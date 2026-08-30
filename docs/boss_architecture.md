# Boss framework architecture (`c_src/boss/`)

This document describes the reusable native boss framework, the exact
source mapping conventions, and the documented deviations. It was
written with the first two ports (MechaBirdo and Kraidgief); the
full-game milestone since implemented every remaining IWBTGR 1.5.3 boss
on the same framework (`boss_tyson.h`, `boss_dracula.h`,
`boss_clowncar.h`, `boss_road.h`, `boss_misc.h`, `boss_guy.h`) — the
complete catalogue and full-game validation live in
[iwbtgr_boss_coverage.md](iwbtgr_boss_coverage.md).

## Design

A boss is an ordinary exact-layer entity (an `XB_BOSS_*` class in the
pack) that additionally owns one **compact native slot**:

```
IWXBossState (c_src/boss/boss_types.h, 148 bytes)
  def, ent          which boss definition drives it; its body xent
  phase, timer      the source phase int + master frame timer
  alarm[8]          GM alarms (set to N, fires N steps later)
  hp, dmg           stage hit points (down) / cumulative damage (up)
  wp_ent[3]         weak-point xent indices (hidden XB_WEAKBOX entities)
  wp_dmg[3]         damage routed in since the boss last consumed it
  p[10], f, sprite  per-boss scalars, flag bits, animation-state enum
```

`IWXState` embeds `boss[IWXB_MAX]` (4 slots) plus `n_boss`; slots are
zeroed on every room load, so death/retry resets a fight exactly like the
source's room restart, and no allocation ever happens mid-episode.

The framework (`boss.h`) provides the shared machinery, each boss file
(`boss_birdo.h`, `boss_kraidgief.h`) is a slim transliteration of that
boss's GML on top of it:

- **Slot lifecycle** — `iwxb_slot()` find-or-creates by body entity and
  runs the per-boss init exactly once (the Create event). It works
  identically for bodies placed in the room record (MechaBirdo) and
  bodies spawned mid-room by a trigger op (Kraidgief), which is how the
  two arenas differ by construction.
- **Hit points / phases** — `iwxb_take()` consumes routed weak-point
  damage with GM's collision→step one-frame latency and an optional
  invulnerability-window countdown; threshold checks in the boss step
  perform the phase transitions (Birdo: sequential 30/15/5 stage HP;
  Kraidgief: cumulative damage 15/25/120, exactly the source's
  `phase<1 && damage>=15` chain).
- **Timers / attack state machines** — the master `timer` plus GM
  alarms (`iwxb_alarm`). Both source bosses are timer-driven `if
  (timer==K)` chains; the ports keep the literal constants
  (`600125`, `900700`, ...) so every line is diffable against the GML.
- **Weak points (moving hitboxes)** — hidden `XB_WEAKBOX` entities
  whose masks are the source hitbox sprites (`sprBirdoAntenna` x10,
  `spr2x2` x32/x45x44, `sprKraidgiefHitbox`, `sprKraidgiefEyebox`).
  The boss places or parks them per animation frame — MechaBirdo's
  hitboxes park at -9999 while she attacks (positional invulnerability,
  verbatim from the source followers), Kraidgief's ride the per-frame
  action-point table of his current sprite.
- **Player bullets** — two routing idioms, matching the two source
  idioms: *push mode* (`iwxb_route_bullet`, called from the bullet's
  collision phase) consumes bullets on weak-point overlap and
  accumulates `wp_dmg` (MechaHitbox's `Collision_bullet` + next-step
  apply); *pull mode* (`iwxb_pull_bullets`) lets a boss destroy
  overlapping bullets in its own step at their pre-move positions
  (Kraidgief's `instance_place(bullet)`). Kraidgief's body also
  *deflects* non-consumed bullets at `choose(45,90,135,-45,-90,-135)`,
  speed 16 kept — deflected bullets can still be eaten by the weak
  point a frame later, which is exactly how shots land on his face in
  the source.
- **Projectile patterns** — pack templates + spawn helpers.
  `iwxb_spawn_visual` refuses to crowd out gameplay entities (keeps 16
  slots free) so the debris rain can never starve a Hadouken.
- **Arena transitions / completion** — `iwxb_goto_room` (pending room
  switch honoring target playerStart), `iwxb_set_flag` (progression
  gflags), `iwxb_kill_player`; camera control for `XCAM_KRAID`
  (`lock` / `piledriver` / one-frame `voffset` quake — cameraKraid.gml
  verbatim). Flag-gated arena states (fight won) compile to room-enter
  op programs (`XOP_IF_FLAG` + teardown ops + `XOP_CAM_MODE`), so a won
  arena loads as the source's cleared corridor.
- **Determinism** — every random call site maps to the environment's
  seeded RNG through `iwxb_irandom/irandom_range/random/random_range`,
  with the source distributions (`irandom(3)+1+walk_counter`,
  `choose(...)`, `random(room_width)`, `random_range(0.99,1.01)`).
  Deterministic replay is asserted per boss and for the synthetic
  framework boss.

### Overhead when no boss is active

All boss code is reached from exactly two places: the per-class entity
dispatch (only `XB_BOSS_*`/support classes ever call in — rooms without
those classes never execute a line), and the player-bullet step, which is
gated by a single `n_boss != 0` integer compare. A room with no boss
keeps `n_boss == 0`, so the entire framework costs one compare per live
bullet per frame — measured as noise-level in the A/B benchmark
(`docs/boss_architecture.md` "Performance" below; harness
`scripts/bench_boss.py`).

### The synthetic test boss

`XB_BOSS_TEST` (in `boss.h`) exercises every framework feature with no
game content — template-parameterized HP/phases/attack period/i-frames/
death flag — and is what `tests/test_boss_framework.py` compiles a tiny
pack around. It doubles as the reference for wiring a new boss.

## The two ported bosses

### MechaBirdo — `rMechaBirdoBoss` (simple; 208 source lines)

Source: `objects/MechaBirdo.gml`, `MechaHitbox{,2,3}.gml`, `MechaEgg`,
`EggPlatform`, `EggHitbox`, `BirdoLaza`, `FlyGuy`. Selection rationale:
the smallest complete dedicated-arena boss, and the classic
sequential-phase shape (three hitbox objects with 30/15/5 HP acting as
phases 1..3).

Ported exactly: the Create pre-advance of 128 walk-in frames (the
source's "moon already hit the floor" fudge, kept verbatim); walk-in
`x = max(620, x-0.4)`; idle bobbing `y += dir*phase` between 739 and
963; alarms 240/350 (phase-1 attack), 2/150 (phase-2), 2/100 (phase-3),
2/200 (laser pair, idle-gated), 2/550 (three FlyGuys once x==620),
2/400 (four FlyGuys in phase 3); attack = image_speed 0.15 on the
4-frame body, egg spat at Animation End at `(x-235, y-447)`; eggs drift
at `-eggspeed` (1, then 3 from phase 2) carrying three rideable
137px platform strips (+ the killer hitbox on phase-3 eggs);
`BirdoLaza` at `mmf_speed(-75) = -9.375`; FlyGuys rise at 5.625, then
re-aim at the player every 50 frames at constant speed, and knock the
Kid back exactly like the BIRD ("it's just a copy of bird" — the same
knockback branch in the engine). Death: eggs freeze, the body sinks 2
px/f, and below y 1507 the fight ends with
`room_goto(rFactoryOutskirts)`; `savedata("orb_birdo")` (set by the
OrbBirdo pickup in the factory outskirts) skips the whole fight on room
entry, warping to (32,624).

### Kraidgief — `rKraidgiefBoss` (complex; 614 source lines)

Source: `objects/Kraidgief.gml` plus KGHitbox / KGEyebox / KGHadouken /
KGFireDown / KGFireSide / Blanka / KraidgiefDebrisSpawner /
KraidgiefDebris / KraidgiefFallingSpike / KraidgiefCeiling /
cameraKraid / OrbKraidgief, and the arena trigger whose once-code
(`instance_create(128,896,Kraidgief)`) spawns him. Selection rationale:
the largest non-final boss in the game, and the widest mechanical
spread — spawned (not placed) body, five phases, RNG attack selection,
a repel-mechanic weak point with escalating thresholds, per-animation
moving hitboxes, per-frame precise body masks that kill on touch AND
deflect bullets, arena destruction, minion spawns, camera scripting.

Ported exactly: the rise intro (1 px/f from y 896 to 384 under the
locked quaking camera); phase 0 walk bursts at `mmf_speed(41)=5.125`
with the left-wall clamp at -64, chop/punch selection `irandom(1)`
after two right-walks, roar vulnerability windows (`alarm[0]=80/60`);
the 15-damage lariat transition (walks right to x=256, rises at 2.5
px/f shredding the KraidgiefCeiling solids it touches, debris cadence
kept via the spawner-alarm check); phase 1 at y=64 — the eye duel
(`eye_damage > eye_damage_max` repels him right, otherwise he advances
left; thresholds grow with `walk_counter`), specials `rng2 =
irandom(2)+1` (ChargeUp dash at 3.75, Headbutt with the source's
origin-fudge x/y nudges, triple Hadouken at `mmf_speed(-75)` on frames
600140/600240/600340), random falling-spike drops (`irandom(11)==0`
per spike per walk-end), and the grab at x<=-64 (phase 3); phase 2 at
25 damage — the charge to x=150 crushing every destructible block,
permanent AngryStand vulnerability, Blanka waves every 300 frames
placed by the player's live height tier, and the giant fire
(down/side variant aimed by `player.bbox_bottom>350`); death at 120 —
the four fixed-position death fires, the sink, floor spikes and
Blankas cleared, camera released. OrbKraidgief sets `orb_kraidgief`
(checkpointing, as all orbs do) and the exit warp leads to rMegaman
(17,407). A set flag tears the arena down to the source's empty
corridor at room entry.

## Documented deviations (boss layer)

These extend the fidelity contract §7 table; everything else is
transliterated from the source GML. The consolidated, classified
deviation list for the frozen pack lives in
[iwbtgr_known_deviations.md](iwbtgr_known_deviations.md).

| # | deviation | source | engine | why |
|---|---|---|---|---|
| B1 | SPD piledriver cutscene | the phase-3 grab plays a ~570-frame scripted piledriver ending in gameOver | the kill lands at the grab-close frame; death counts, room resets | deviation #2 (death-timing compression); the cutscene is pure presentation and unavoidable once grabbed |
| B2 | `skipButton()` intro skip | holding the skip key jumps the rise intro | not mapped (no such input in the action space) | input outside the 12-action space, like ErrorTrap's mouse |
| B3 | dev cheat key | `KeyPress_75` ("K") deals 5 damage with a `settings("kraidgief")` unlock, else spawns ErrorTrap | not implemented | debug-only path, gated by dev settings |
| B4 | debris RNG stream | debris consumes the shared GM RNG stream | env-seeded RNG, same call sites/distributions | deviation #1 (RNG policy); debris is visual-only |
| B5 | MechaHitbox3 `wait` | sets `wait=1` for 50 frames but never reads it | omitted | vestigial in the source (no reader) |
| B6 | boss-rush hooks | `defeat_bossrush(...)`, `global.bossrush` branches | not implemented | rBossRush is a meta-mode outside the milestone |
| B7 | ceiling tile visuals | destroyed KraidgiefCeiling deletes its depth-900 tile | the solid + entity vanish; the schematic renderer's static tile layer is unchanged | rendering stays schematic by design |
| B8 | VicViper vertical input | flight reads `global.input_v` (a dedicated up/down axis) | jump held = up 4 px/f, otherwise down 4 px/f; horizontal from the normal move axis; held shoot fires under the source's 3-active-bullet cap | the 12-action space has no up/down axis; this is the only injective mapping that keeps both verticals reachable every frame |
| B9 | Deadcula true-form flip | the reveal flips `image_xscale` by facing | the shootable mask swaps in unflipped; facing is kept (p4) for the death animation | the true-form collision sprite is horizontally symmetric at gameplay level; flip is presentation |
| B10 | orb flag timing (Dracula/Mother) | `global.orb_on_room_change` applies the flag at the next room change (with the save) | the flag + checkpoint land at pickup (all orbs uniform); OrbDracula's Alarm_0 warp itself is exact (185f) | visible only if the player dies between pickup and the room change — a degenerate window that the source itself handles murkily (the alarm dies with the orb) |
| B11 | skip/dev keys (m8 bosses) | `skipButton()` on the Dracula/GuyHead intros; dev damage keys | not mapped | same class as B2/B3: inputs outside the action space / debug-gated |
| B12 | Samus escape cameo | a path'd sprite flies out during the Metroid escape | excluded as visual (no collision events in source) | the rMetroid trigger targeting her is the one recorded boss_exception_note |

## Performance

Methodology: interleaved best-of-3 A/B against the pre-boss commit
(container noise is ~±20%), `scripts/bench_boss.py`. Results in the
milestone report; the acceptance bar is that ordinary rooms (legacy
levels and non-boss iwbtgr rooms) show no material regression, boss
arenas are full-speed, and many parallel boss environments scale
linearly.

Full-game milestone A/B (HEAD vs the boss-framework commit,
interleaved best-of-3, same container): arena_birdo −1.6%,
arena_kraidgief +5.0%, parallel_boss −5.2%, parallel_normal +4.3% —
all inside noise. The new arenas at HEAD (single env, mixed 12-action
policy): rDraculaBoss ≈681k steps/s, rGuyBoss ≈334k, rBowserBoss
≈215k, rMetroid ≈97k, rGuyRoad ≈94k, rGuyFortress2 ≈21k (the 5600px
room holds ~750 live entities); every arena is orders of magnitude
above the 50 Hz real-time bar.
