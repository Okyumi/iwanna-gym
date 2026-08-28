# IWBTGR 1.5.3 boss coverage and mapping plan

Status after the boss-framework milestone: the framework
(`c_src/boss/`, see [boss_architecture.md](boss_architecture.md)) plus
two fully playable source bosses. This document accounts for the two
converted arenas and lays out the documented mapping plan for every
remaining boss.

## Converted arenas (fully playable)

Every placed instance in the two arenas is implemented or excluded with
a recorded justification, under the same build-failing coverage gates as
the non-boss rooms (`build/games/iwbtgr_1_5_3.coverage.json`,
`exact.implemented_boss`):

| room | boss | implemented instances | notes |
|---|---|---|---|
| `rMechaBirdoBoss` | MechaBirdo (simple pick) | `MechaBirdo` 1, `MoonSmall` 1 (falls in with the Kid, cc `vspeed=6`) | + statics (blocks, blockKill rows), visual `MechaWarning`/kumo deco; runtime spawns: eggs, egg platforms, egg hitboxes, lasers, FlyGuys, 3 weak points |
| `rKraidgiefBoss` | Kraidgief (complex pick) | `KraidgiefCeiling` 110, `KraidgiefFallingSpike` 46, `blockTrapDestructible` 11, `OrbKraidgief` 1, spawn `trigger` 1 (+ the 47 `spikeUp` floor row converted to destroyable killer entities) | runtime spawns: Kraidgief body, hitbox/eyebox weak points, Hadoukens, down/side fires, Blankas, debris spawners/debris |

Progression: MechaBirdo's death warps to rFactoryOutskirts where the
`OrbBirdo` pickup sets `orb_birdo` (flag 2) — re-entering the arena then
skips the fight to (32,624), exactly as `savedata("orb_birdo")` does in
source. `OrbKraidgief` sets `orb_kraidgief` (flag 3) in the arena
itself; the set flag tears the arena down to a corridor on entry. Both
flags feed the existing EntranceTele six-orb gate and BossTeleporter
conditions from the non-boss milestone.

Tests: `tests/test_boss_framework.py` (7, synthetic boss),
`tests/test_iwbtgr_bosses.py` (14, both fights end-to-end incl. a
pinned reference trace, `tests/fixtures/iwbtgr_trace_birdo.sha`).

## Remaining bosses — mapping plan

Source-line counts are the boss object alone; support objects listed.
"Framework fit" names the primitives that carry the port; none of the
remaining bosses needs a new framework concept — each is one slim
`boss_<name>.h` + templates/emitters + tests, following the two shipped
ports.

| boss | where | source size | support objects | framework fit / notes |
|---|---|---|---|---|
| Mike Tyson | inside `rGuy1` (gameplay room) | 358 | TysonFist, TysonFireball, TysonStar, TysonReferee (visual), TysonDoor/TysonBrick (already imported: static/destructible) | placed boss coexisting with a converted gameplay room — the arena trigger that currently compiles to a recorded no-op (`boss_exception_notes`) becomes his activation; timer attacks, weak point face, `orb_tyson` (flag 1); validates "boss inside a normal room" |
| Dracula | `rDraculaBoss` | 119 (+ DraculaIntro 206) | DraculasFace, Dracform (staircase), DraculaIntro (the wine glass you shoot to start) | shoot-to-start = pull-mode bullets on an intro entity; RNG attack selection (`choose`) like Kraidgief's rng2; teleport pattern via timers; `orb_dracula` (flag 6) |
| Bowser → Wart → Wily | `rBowserBoss` | 14 + 61 + 55 (chain controller logic in room/warp code) | BowserBomb/Explosion/Floor/Wall, WartPoof, WilyFirePillar/Fireball, FallingCeiling(Spike) | three sequential slots (IWXB_MAX=4 was sized for this); arena hazards are existing class shapes (falling ceiling = KGSPIKE-like); `orb_bowser` (flag 4) |
| Mother Brain escape | `rMetroid` (gameplay room) | MommyThinker 132 + Samus 31 | MotherBrainPlatform (visual), the already-implemented Metroid latch + Tourian turrets/barrier | the two triggers currently no-op'd in rMetroid arm the fight; escape-timer choreography = timers + GOTO_ROOM; `orb_mother` (flag 5) already wired to BlownEntrance/TourianBarrier |
| Devil Dragon | `rGuyTower` (gameplay room) | 374 | DragonFire, DragonFace, DragonBlock (15 placed), DragonMarker/2, DragonDevilism* | chase boss: sampled-path/marker-driven movement (keys pool + markers already in the pack format); tower camera already exact; `orb_dragon` (flag 7) |
| The Guy | `rGuyBoss` | GuyFirst 549 + 12 Guy* objects | GuyHead/Mouth/Tooth/ToothShooter, Guy*Bullet family, GuyDarkness, GuyPlatform (already implemented) | the largest table: multi-slot (head + hands-style parts as weak points), many projectile templates; completion = `orb_guy` (flag 8) + ending rooms |
| Gradius segment | `rGuyRoad` section | VicViper 191 + GradiusBoss 66 | GradiusBugz/Drones/DroneBullet/Fruit/Marker | blocked on the VicViper *player vehicle mode* (a player-state feature like the cart, not a boss-framework gap); the boss itself is plain slots+templates once flying exists |
| Sinistar | `rGuyRoad` | 73 | — | small chase actor during the cart ride; one class |
| RoadMoon | `rGuyRoad` | (with MoonBigFall support) | MoonBigDeco (visual) | scripted set-piece on the road; keys-pool path |
| LuBooHoo | `rGraveyard` | 22 | — | trivial (one spawner-style actor) |
| Arkanoid minigame | factory area | ArkaBall 133 | ArkaPlatform, ArkaBrick(Short) | self-contained minigame: ball+paddle physics in one class + brick grid as destructibles |
| Boss Rush | `rBossRush` | BossRushController 55 + RushTeleporter | — | meta-mode once individual bosses exist; `defeat_bossrush` hooks are already stubbed as a documented deviation (B6) |

Suggested order: Tyson (boss-in-gameplay-room validation), Dracula
(intro-object pattern), Bowser/Wart/Wily (multi-slot), Mother Brain
(escape + existing flag wiring), Devil Dragon, The Guy, then the
vehicle-gated Gradius segment alongside the minor set-pieces, and Boss
Rush last.

Regenerate the instance accounting after any converter change with
`python -m iwanna_gym.games.iwbtgr_1_5_3 build <source>` — an
unaccounted instance in a converted room fails the build.
