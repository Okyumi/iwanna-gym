# IWBTGR 1.5.3 boss coverage — full-game report

Status after the full-game milestone: **every gameplay-relevant boss
and boss-linked sequence in the source is implemented**, and the game
is completable end-to-end inside the engine — from the rGuy1 spawn,
through all eight boss encounters and the six-orb EntranceTele gate,
to the completion event in rEnding. The coverage gates in
`build/games/iwbtgr_1_5_3.coverage.json` fail the build if any placed
instance in a gameplay room is unaccounted for; `excluded_boss` is
now empty — the boss bucket holds only implemented content (22
placed classes, 261 instances; runtime spawns come from templates on
top of that).

The proof artifacts are executable:

- `iwanna_gym/games/iwbtgr_1_5_3/drivers.py` — scripted reference
  drivers for every boss segment plus `run_full_game()`, one
  deterministic session (seed 11, ~57k frames, zero deaths) covering
  the complete progression;
- `tests/test_iwbtgr_fullgame.py` — the segmented reference suite (the
  full run, the gate both ways, refight skips, the escape countdown,
  the OrbDracula exit warp, the Gradius victory sweep, the
  Sinistar/viper interaction);
- `tests/fixtures/iwbtgr_trace_fullgame.sha` — the pinned waypoint
  trace of the full run (regenerate via
  `scripts/record_reference_traces.py`).

## The boss catalogue

| # | boss / sequence | room | flag | port |
|---|---|---|---|---|
| 1 | Mike Tyson | inside `rGuy1` | `orb_tyson` (0x2) | `boss_tyson.h`: door intro, timer-driven fireball patterns, face weak point with vulnerability windows, arena doors; orb in-arena; refight skip removes doors + boss |
| 2 | MechaBirdo | `rMechaBirdoBoss` | `orb_birdo` (0x4) | `boss_birdo.h` (framework milestone): 3 phases (antenna 30 / eye 15 / mouth 5), eggs + egg platforms, lasers, FlyGuys; death warps to rFactoryOutskirts where the OrbBirdo pickup sets the flag; flag skips the fight on re-entry |
| 3 | Kraidgief | `rKraidgiefBoss` | `orb_kraidgief` (0x8) | `boss_kraidgief.h` (framework milestone): intro rise, hadoukens, lariat ceiling clear, fires, Blanka waves, SPD grab, 120-damage death teardown; orb in-arena; exit warp to rMegaman |
| 4 | Koopa Clown Car (Bowser → Wart → Wily) | `rBowserBoss` | `orb_bowser` (0x10) | `boss_clowncar.h`: three sequential phases in one slot — Bowser bombs (solid bounce + push-out, shootable, body-bbox explosion contact), Wart banzai bills with accelerating speedmod, Wily capsule (hover paths, wily balls, fireballs, falling-ceiling sweep + switch + spikes, bowser floor); GM path playback with per-point speed factors (pSwoosh / pDash / pWilyHover); orb in-arena |
| 5 | Mother Brain | `rMetroid` | `orb_mother` (0x20) | `boss_misc.h`: glass shatter -> 35 hp -> turret/dispenser/glass teardown; the chamber-floor escape trigger removes her and starts the 3000-frame countdown (out of TIME kills anywhere in the room); orb on the escape route; exit to rFactoryOutskirts |
| 6 | Dracula → Deadcula | `rDraculaBoss` | `orb_dracula` (0x40) | `boss_dracula.h`: DraculaIntro cutscene (2005f), teleport pattern, apples/moons/death spirals/ectoplasm, Deadcula walk-in with the 4x true-form reveal at T=320 (shootable mask swap); OrbDracula pickup arms the source Alarm_0: 185 frames later the player is warped to rFactoryOutskirts (3040,960) — the arena's only exit |
| 7 | Road Dragon | `rGuyRoad` | `orb_dragon` (0x80) | `boss_road.h`: the moon-road ride under the cart camera, the dragon's view-lock override + inside-view kill + choreographed view pans (gameplay, not cosmetic), facing-dependent shooting windows, GM editor-bbox bounce band, devilism pillar stages, the flag-78 chase; death checkpoints the player into rGuyFortress1 |
| 8 | Gradius segment (VicViper + GradiusBoss) | `rGuyFortress2` | — (route section) | `boss_road.h`: mount freezes the kid and wakes the field (bugz -6.25, drones -6.25, boss -5); marker-armed bugz aim at the ship; drones retreat + 3-shot spread; boss fruit spirals (hp 10); held-shoot autofire under the 3-active-bullet cap; victory sweeps all gradius actors + in-view destructibles and flies the rider home on the invisible platform |
| 9 | Arkanoid + Sinistar | `rGuyFortress2` | — (route section) | `boss_misc.h`: zone-following paddle, 45° ball launch, circle-vs-rect brick bounce (82 bricks, +/- speed per brick type); last brick wakes the Sinistar — accelerating player chase, bullet pushback (+32), and the source's Collision_VicViper: an active Sinistar touching the mounted viper kills it |
| 10 | The Guy (GuyFirst → TheGun → GuyHead) | `rGuyBoss` | `orb_guy` (0x100) | `boss_guy.h`: GuyFirst phases (projectile/grenade/bounce volleys, wily pillars, pGuyJump dash paths, phase-2 giant bounce with the volley redirect), TheGun pickup, the GuyHead cutscene (hands-off until T=285), the Geye arming cycle with teeth / tooth shooters / glass shots / mouth, spin phases; death opens the rEnding warp |

Boss-linked set-pieces also in: RoadMoon roll-in (rGuyRoad), MoonSmall
falls (both arenas + road), the LuBooHoo torch that absorbs the
fortress BowserFireClassic (fire-sink marker), the fortress2 walljump
strips and Guy platforms, and the rGuyBoss glass panes' shot
interactions.

## Full-game progression (validated end-to-end)

`run_full_game()` (seed 11) — zero deaths, waypoint ticks pinned in
`tests/fixtures/iwbtgr_trace_fullgame.sha`:

rGuy1 spawn → Tyson (0x2) → Zelda → Graveyard → MechaBirdo →
rFactoryOutskirts + OrbBirdo (0x6) → GuyEntrance → rGuy1 →
KraidgiefLair → Kraidgief (0xe) → rMegaman → ClownCar (0x1e) →
rFactoryOutskirts → rGuy1 → rMegaman → rMetroid: Mother Brain +
escape trigger + orb under the live countdown (0x3e) → Castlevania →
Dracula (0x7e) → auto-warp to rFactoryOutskirts → GuyEntrance →
**EntranceTele gate passes with exactly the six orbs** → rGuyRoad:
Dragon (0xfe) → checkpoint into rGuyFortress1 → Labyrinth →
rGuyFortress2: Gradius victory, then Arkanoid + Sinistar wake →
rGuyTower → rGuyBoss: GuyFirst → TheGun → GuyHead (0x1fe) → rEnding →
**completion event (game_completions=1, last_event=4), run resets**.

The gate also fails correctly: entering the teleporter with zero orbs
kills (test_entrance_gate_kills_without_orbs).

## Verification inventory

- 240 tests green (`/tmp/runtests.py`), including 13 in
  `test_iwbtgr_fullgame.py` and the earlier per-boss suites
  (`test_iwbtgr_bosses.py`, `test_boss_framework.py`).
- Three pinned deterministic traces: rGuy1 mixed-action, the Birdo
  fight, and the full-game waypoint trace.
- Determinism: identical seeds replay identically (the fixture tests
  recompute the digests from live runs every suite invocation).

## Exceptions and deviations

- `excluded_boss` is empty. The only boss-adjacent exception note is
  the rMetroid trigger targeting **Samus** — her escape cameo is a
  path'd sprite with no collision events (visual, documented in
  `exact.py` VISUAL_CLASSES).
- rBossRush / `defeat_bossrush` hooks remain out of scope (meta-mode,
  deviation B6), as do menu/credits/unlock rooms (meta rooms).
- Behavioral deviations carried by the boss layer are tabulated in
  [boss_architecture.md](boss_architecture.md) (B1–B12): the RNG
  policy, death-timing compression, skip/dev keys outside the action
  space, the VicViper vertical input mapping, the immediate orb-flag
  semantics, and the schematic-rendering visual notes.
