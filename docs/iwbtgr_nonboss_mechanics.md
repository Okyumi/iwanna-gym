# IWBTGR 1.5.3 — non-boss mechanics catalog (source semantics)

Authoritative reference for milestone "non-boss room completion". Every fact
below was read from the IWBTGR 1.5.3 source tree (gm82save text export of
`IWBTGR.gm82`, clone `aut0mat1clol/IWBTGR-Autosplitter-mod` @ `244c325`);
file/event references are given per class. Canonical character is **The Kid**
(`global.char==0`): `dot/vic/owater/boshy` branches are dead, and
`physics=settings("physics")` defaults to **0** ("yutu" physics — the values
already verified in the basic-loop milestone).

## Unit conversions (scripts/)

| helper | value |
|---|---|
| `mmf_speed(n)` | `n/8` px/frame |
| `mmf_animspeed(n)` | `n/100` frames/frame (2-arg form lerps by `speed/31.25`) |
| `mmf_direction(n)` | `n*90/8` degrees (32-direction system, 11.25° steps) |
| `mmf_direction_to(d)` | `round(d/360*32) mod 32` (quantize to 32 dirs) |
| `mmf_pinballspeed(n)` | `n/10` |

## The 14 non-boss gameplay rooms

rCastlevania, rFactoryOutskirts, rGraveyard, rGuy1, rGuyEntrance,
rGuyFortress1, rGuyFortress2, rGuyLabyrinth, rGuyRoad, rGuyTower,
rKraidgiefLair, rMegaman, rMetroid, rZelda — 230 distinct object classes,
6,717 placed instances, plus classes only ever spawned at runtime
(HoverShot, Metroid, RollingRocks, Playstation, Spaghettio, KillPill,
tetrisBlock, BIRD, MedusaHead spawns, DumbBugz, GutsMan, KillPlane,
BowserFireClassic, FireSometimesUpside, CUTE_KITTY_BOOM, SnifitBullet,
DestroyedSpike*, DestroyedPlatform*, DeadBugz*, MedusaDead* — `*` cosmetic).

Boss/system rooms excluded from this milestone: rTitle, rInit, rFiles, rDev,
rCredits, rEnding, rUnlocks, rBossRush, and the six boss rooms.

## Player mechanics added this milestone (objects/player.gml)

The Kid always uses `mask_index=sprMask`: **rectangle** mask, origin (17,23),
bbox 12..22 × 11..31 → hitbox **x−5..x+5, y−12..y+8 (11×21 px)**. (The
previous engine used y−11..y+8; exact mode now uses the source box — recorded
in the fidelity contract as a fixed deviation.)

* **Walljump** (Step "walljump" section) — trigger: bbox distance to a
  `WalljumpL`/`WalljumpR` strip `< 2` px (children count: `yellowall*`,
  `WeirdYellowWall*`).
  - Slide: if `place_free(x,y+2)`: `hang=1`, `vspeed=2` each frame.
  - Kick (jump **held**, plus press of away-direction or jump, gated exactly
    as in source): plain walls `vspeed=-9, hspeed=±15`, `altj=2, walljump=2,
    walljumpboost=0`; near `WeirdYellowWall*`: `walljumpboost=24,
    walljumpdir=±1` (24 frames of forced input at maxSpeedBoosted=4);
    near `yellowall*`: `carted=0, walljumpboost=-1, hspeed=±10, vspeed=-10`.
  - No-jump push-off: `hspeed=±3`.
  - `walljumpboost<0` decay mode: input ignored; every 10th `altj` frame
    `hspeed-=sign(hspeed)`; `vspeed+=0.1` extra per frame (non-physics);
    ends when `abs(hspeed)<4`. `walljump>0` frames cancel gravity.
  - Wall sprites are rectangle masks: sprWallL/R = 16×32 half-tile strips,
    sprYellowallL/R = 6×32 slivers.
* **Couch/cart decel** (movement section): while `vspeed<-8.5` (non-physics):
  `vspeed += 0.71` per frame, or `+= 0.1` if jump is held.
* **Platform landing** (`Collision_platform`): fires on mask overlap with any
  `platform`-descendant when `y - vspeed/2 <= plat.y`; sets `djump=1`; if
  `plat.vspeed>=0`: snap `y=plat.y-9` (revert if that lands inside a solid
  while plat moving down), `vspeed=plat.vspeed`; `onPlatform=1`,
  `walljumpboost=0`, `carted=0` (re-carted if the platform is the Cart's).
  `onPlatform` clears when `!place_meeting(x,y+4,platform)`.
  Platform carry (movingPlatform Step): a platform moves the player standing
  on it (probe `instance_place(x,y-2,player)`): `player.y += yspeed` and, if
  `!nopush || onPlatform`, `player.x += hspeed` when that spot is free.
  Platforms use a two-channel vertical model: upward motion is carried in
  `yspeed` (applied manually before the carry), downward in `vspeed`
  (built-in); the channels are swapped at the end of each Step.
* **Jump rules** (scripts/playerJump.gml): ground = `place_meeting(x,y+1,
  block) || onPlatform || place_meeting(x,y+1,objWater)` → `vspeed=-8.5`,
  `djump=1`; else if `djump || place_meeting(x,y+1,objWater2)` →
  `vspeed=-7`, `djump=0`.
* **Water**: `objWater` collision: `djump=1`, `vspeed=min(2,vspeed)`;
  `objWater2`: `vspeed=min(2,vspeed)` only (but grants unlimited −7 jumps
  via the rule above).
* **frozen / cutscene / stoned / birded / fished**: `frozen` zeroes h and
  blocks jump/shoot (set by triggerLockControls, Metroid latch, GutsMan,
  ErrorTrap; ErrorTrap unfreezes after 100 frames — the others never do);
  `stoned=100` (MedusaHead touch) with random knockback
  `hspeed∈[-20,20], vspeed∈[-10,10]`, controls locked while it counts down;
  `birded=10` (BIRD touch, same knockback + `djump=0`); `fished=20`
  (RoadCheep touch: `hspeed=-8, vspeed=-8, carted=0`).
* **Death check**: end of player Step, `instance_place(x,y,playerKiller)` →
  `killPlayer` (playerKiller itself has no collision event). Kid death:
  `global.death+=1`, gameOver → room restart at the checkpoint.
* **Kill-on-land fire state**: rGuy1 triggers set `player.fire=1` then
  `fire=2`; while `fire=2`: touching ground (`place_meeting(x,y+1,block)`)
  kills; overlapping objWater/objWater2 clears it. (No other source sets
  `fire`.)
* Cart riding: `carted=1` → `x += Cart.hspeed` per frame.

## View + activation model

`game_start.gml` gives every room a fixed 800×608 view with **no** follow
object; camera objects drive it:

* **cameraHard** (11 rooms) — per-screen snap:
  `camx=median(0, floor(px/800)*800, room_w-800)`,
  `camy=median(0, floor(py/608)*608, room_h-608)`; runs in EndStep, plus
  once at room start. rMetroid with `settings("smoothmetroid")` (**default
  1**): past `camx>=2400` the y-camera chases the player smoothly within a
  ±96 band.
* **cameraCart** (rGuyRoad) — follows `Cart.x+54-400` while the cart lives
  (kills the player if the view passes them: `view_x > player.x`); after the
  crash follows `max(min(view, 22400), player.x-400)`.
* **cameraTower** (rGuyTower) — smooth chase `camy=(camy*19+py-304)/20`
  clamped; fixed (800,2432) once `player.x>800`.
* **rGuyEntrance** has no camera: static view (0,0).

`activation_update()` (called by cameras when the view crosses a screen /
moves 32px): deactivates all playerKiller/block/trigger/platform/deco, then
activates everything whose bbox intersects the 3×3-screen region
`[view−(796,604), +2392×1816]`, force-activates WheelTrap, MoonBigFall,
KillPill, DumbBugz (+boss classes), and re-activates the neighborhood of
every movingPlatform. **rGuyLabyrinth never deactivates anything.**
Deactivated instances do not step and do not collide. `inside_view()` /
`inside_active()` use the instance bbox vs the view rect / the 3×3 region
∓8px. movingPlatform additionally freezes itself (undoes its own motion)
whenever its bbox leaves `[view_x−800, view_x+1600] × [view_y−608,
view_y+1216]`.

## Collision masks (pack v3)

gm82 `sprite.txt` supplies frames, origin, `collision_shape`
(0=precise, 1=rectangle), `alpha_tolerance`, `per_frame_colliders`, bbox.
The pack now embeds, for every sprite a non-boss class collides with:
per-frame (or single/union) bitmasks decoded from PNG alpha
(> tolerance), clipped to the bbox, with origin; instances scale them
(`image_xscale/yscale`, negatives flip about the origin). Collision =
GM-style integer pixel sampling over the intersection of transformed
bboxes. Rotation appears only in: FactorySpinner1/2 (fixed 12-step angle
ramps — pre-rasterized per step), the SnifitCannon 315° laser (rotated
rect, SAT test), and near-circular tumbling debris/moons (sampled with
inverse rotation). Key masks: sprMask 11×21 rect (player);
sprFireMarker 34×65 precise ×18 frames; sprCycleSpikeUp/Down 35-frame
precise; sprGuySpikeTrapBarrier 6-frame 96×9 precise (frame 0 open);
sprZeldaCollision 256×480 precise scaled to the room (rasterized offline
into static solids); maskTrigger 32×32 rect (all triggers, scaled).

## Trigger system (objects/trigger.gml — 135 placed instances)

Rect region (maskTrigger scaled). Post-movement each frame while the player
overlaps: if `!active`: `active=1`, `alarm[0]=2`, run the **t** code once
per touch and set `target.active=1`; run **o** once ever (`lock`); run **c**
every frame. The 2-frame alarm then clears `active` (and `target.active`),
so a standing player re-fires `t` every 3rd frame — this cadence is
load-bearing (KumoPlatform drift) and is reproduced exactly. Targets are an
instance id, an object class (= all instances), `player`, or `id` (self,
pure code). All 135 creation-code programs (plus warp `code=` strings and
the two room-entry side effects) are compiled offline to a small op list;
**an unrecognized code string fails the build** (coverage gate).

Room-entry side effects (scripts/room_start.gml): `global.castleboost=1` →
spawn with `vspeed=-24` once; `global.factory_ceiling_flag` 1 → destroy
FactoryCeiling+Ryu, 2 → keep them; both reset RyuButton to pressed-off
state. Cart rooms restore cart state on respawn (`player.x>20000` → crashed
cart + wall, else `carted=1`, cart at `player.x-64`).

## Class-by-class semantics (exact constants)

### Static geometry & killers
* `block`, `blockNotMerge`, `blockMini` — solids (already imported).
* `Torizo`, `TysonDoor`, `HillMove`†, `ZeldaCollision`, `tetrisBlock`,
  `TourianBarrier`†, `ShootyBarrier`†, `FactoryCeiling`†, `NatsCat`†,
  `FirstRoomBarrier`†, `blockYoku`, `blockYokuTile`, `FallStair`†,
  `FallingFort`†(pre-activation), `BlownEntrance`† — solid classes with
  behavior (†) or conditions; see below. `blockYoku`/`blockYokuTile` are
  **always solid** (visibility-only reveal within 2px of the player).
* `spikeUp/Down/Left/Right`, `blockKill`, `trapStar`, `Snifit`, `Turbine`,
  `EggHitbox`, `ZeldaFire` (mask mirrors every 8 frames), `ZeldaOldMan`,
  `FirstRoomSpikeWall` (marker), `SoftlockBlocker` (save-blocker region),
  `blockNise` (non-solid 32×32 marker: platform/cart bouncer, witch/crawler
  killer, fake block), `MedusaModifier`, `DumpMoment`, `BulletTrigger`,
  `KumoStopper`, `Bounce{Up,Down,Left,Right}` — static killers/markers.
* `ZeldaSword` — par=block but **solid=0**: touch-kill with its sprite mask.
* `blockFake` — non-solid; destroys overlapping real blocks at room start
  (applied at compile time) and despawns on touch (cosmetic reveal).

### Fire family (all par=playerKiller, sprite set at runtime)
`Fire` starts with **no mask** (`sprite_index=-1`); when armed
(`visible=1` via FireChalice cascade or triggers) it becomes the 18-frame
sprFireMarker precise mask at animspeed 0.5 (loop 8..17 via `index-=2`).
`FireOnce` deadly immediately, dies at animation end. `FireShort` armed →
0.5, loops 6..7. `FireSometimes` armed → 0.3 full 18-frame loop (mask empty
on the "out" frames = flickering). Permanent variants are pre-armed:
`FirePermanent` (0.5, loop 8..9), `FireShortPermanent` (0.5 from frame 6,
loop 6..7), `FireSometimesPermanent` (0.3 loop), `FireSometimesUpside`
(y+=32, yscale −1, 0.3). `FireChalice`: killer; trigger gives `vspeed=6.25`;
on solid contact (or `player.x>800`) arms every Fire-family instance in the
room and dies. `FireGlow` cosmetic.

### Timed / triggered killers
* `FallingSpike` 4-frame shake → `vspeed=10`. `FallingSpike10frame`
  10-frame shake → `vspeed=spd` (10 unless creation code; one rGuyRoad
  instance gets `spd=12.5` via trigger). `FallingSpike10frameUp` →
  `vspeed=-spd`. `FakeFallingSpike` shakes forever. `FallingCave` 20-frame
  shake → 7.5. `FallingBlockTrap` shakes, falls 6.25 at frame 40.
* `CycleSpikeUp/Down` — 35-frame animated masks; triggers set animspeed
  0.3 / 0.7.
* `BoltTrap` — invisible; trigger: `visible=1, vspeed=8.75`.
* `SpikeUpExtend` — while `on`: `y=median(y, player.y, y-4)` (rises ≤4/f
  toward the player, never retreats) with a growing blockKill shaft below.
* `RevealingSpikesUp` — event: rise `vspeed=-4` (clamp ystart−32), 200
  frames later sink +4 (clamp ystart).
* `SpikeTrap` (rGuy1) — crusher: platform on top (y+1) + 64×16 blockKill at
  y+8; trigger: `vspeed=36` slam; floor at y=860, 250 frames, then −1 rise.
* `GraveTrap` — touch starts 0.2 anim; at frame 6 touching kills.
* `Grabby` — invisible killer hand; on activation animates ping-pong
  (±0.3) with per-frame masks.
* `QuickLaser`(+`QuickLaserTimer`) — player touch starts the timer;
  lasers `c=1..7` fire at frames [10,140,200,210,350,400,590]; a laser
  grows from `size=-delay` by 12.5/frame to `length*32`, mask = 1×30 rect
  scaled to `max(1,size)` long, rotated 0/90/180/270. The rMegaman exit
  trigger sets `QuickLaserTimer.active=0` and spawns a block at (2336,576).
* `KillPlane` — spawned at (3200,412): 18.75×17.4-scaled killer,
  `hspeed=-35`, kills outright once `x<player.x`.
* `Higger` — falling painting: `a+=0.2, angle+=a`; kill mask = maskTrigger
  scaled `xscale=7+4*(angle/90)`, `yscale=max(1,264-cos-projection)/32`,
  `x=xstart-64*(angle/90)`; gone past 180°.
* `ErrorTrap` — freezes+pins the player 100 frames; at 165 the dialog falls
  (`vspeed=6.25`) and kills while moving; destroyed if the camera changes
  screens. (Mouse dismiss is outside the action space — documented
  exception; the keyboard-only game is unchanged.)
* `PaintingTrap` — drops 32px (gravity 1) when the player is under it
  (self or +32 probe); kills if overlapping when it lands.
* `WheelTrap` — force-active; trigger → rolls at 7.5, plows through
  blockTrapDestructible (destroying them), spins (cosmetic).
* `FlyingSpike` — trigger → rises 6.25 to y=334.
* `GutsMan` — trigger-spawned: 150-frame jingle, then freezes the player,
  falls 37.5 at their x, kills on platform contact (scripted death gag).
* `trapStar`, `couchTrap` — couch: single-use bounce `vspeed=-30, djump=1`
  (then anim-locks).
* `Hammer`(+`HammerTrigger`) — trigger: falls 6.25, kills on overlap
  (EndStep), becomes a solid on its blockNise marker.
* `TheSpikeYouShoot` — shakes (kills while dormant); shot → 21-frame spiral
  to (2496,2367), becomes a platform, and starts RealYokuController.

### Destructibles & shootables
* `blockTrapDestructible` (249 + spawned) — invisible blockNotMerge solid
  (`coll`, owner-linked) + tile; destroyed only by events (WheelTrap,
  MoonSmall, MoonBigFall, Cart via BiggusBrickus columns, spikeUp `dest`
  chains); destroying one also destroys overlapping Walljump strips.
  `TysonBrick` par of it (1.25-tall solid) — only boss events break them.
* `ShootyBarrier` — solid; each bullet `image_index+=0.2`; destroyed at
  animation end (10 hits with 1-damage bullets... `0.2*damage` per hit,
  sprite has 2 frames).
* `NatsCat` — solid; bullets add `damage` (1 each), Fire contact adds 0.1;
  >25 → CUTE_KITTY_BOOM (20×-scale killer explosion, ~20 frames).
* `ChozoOrb` — killer; shot → destroyed, spawns secret4.
* `RyuButton` — shot: toggles (5-frame cooldown): ON→OFF stops the Turbine
  and converts RyuWind→RyuTrigger (entering that region launches Ryu);
  OFF→ON restores wind. Factory ceiling entry (flag) presses it OFF.
* `PlatformReset` — shot toggle: all movingPlatforms in view get
  `yspeed=-0.25` (slow rise) / reset `y=ystart`.
* `saveVeryHard/Hard/Medium` — bullet hit: invalid (player overlapping
  SoftlockBlocker or a killer) → bullet deflects at a random 32-direction;
  valid → save (50-frame `saveTimer`). Difficulty destroys: Medium if
  diff>0, Hard if diff>1, VeryHard if diff>2. (`bowsercrash`/`crashy`
  creation vars are dead code.) `saveVeryEvil` requires a non-default
  setting — excluded.

### Enemies
* `MedusaHead` — `hspeed=3.75` (spawner: `±3.75·dir`... maker bullets use
  `dir*3.75`), vertical zigzag: `spd+=1` every 5 frames, `dir` flips every
  50, `y+=spd*dir`; at MedusaModifier: recycle (x−=80, hspeed=−1.875) or
  despawn. Touch = stone, not death. Shot → dies.
* `MedusaMaker` — patrols pMedusaMaker (relative, closed) at 12.5; spawns a
  head every 100 frames while the camera is above it.
* `BIRD` — trigger-spawned; re-aims at the player every 10 frames at 7.5;
  touch = knockback+djump loss; shot → dies.
* `Ghoul`(+`GhoulGenerator`) — generator wanders ±0.625 bouncing off
  blocks, spawns a Ghoul every 175 frames when in the active region.
  Ghoul: 31-frame emerge shake, rises (0.2 anim), then walks
  `hspeed=±2` for `600-irandom(50)` frames (kills on touch during the
  walk), hp=4 vs bullets, sinks away.
* `HoverGunner` — every 90 frames (in view, not while dropping): 4
  HoverShots at 3.75/6.25/8.75/10.625 px/f, direction quantized to 32
  dirs, from an 8px muzzle offset (+aim tweaks). Trigger-spawned ones drop
  637px at 1.75. One bullet kills it. `HoverShot` dies on solid blocks.
* `SniperJohn` — 75-frame cycle: aim at `(px, py-5)` on anim frame 10, fire
  4 HoverShots at 3.75/6.25/8.75/10.625 (raw angle); shot → dead.
* `TourianTurret` — 140-frame cycle: re-aim (45° quantized) at 140, fire at
  80 (bullet 6.25 from +28 muzzle).
* `Skwee`(+`SkweeTrigger`) — hangs; trigger dives at 5 (dir 247.5° or
  292.5° by player side); block → dies (still deadly 30f); shot → freezes
  into a solid block. `Crawler` — edge-follows walls at speed 1 (32×32
  probe box), killer; shot → becomes a solid block; blockNise → despawn.
* `DumbBugz` — force-active homing killer at 6.25 every frame;
  trigger-spawned pairs in rMegaman; shot → dies.
* `Metroid` — spawned by metroidTrap (+700,−200): homes at 12.5 (slow 6.25
  after first touch); 100 frames after touching it latches — player hidden
  + frozen (modeled as death 100 frames after contact; escape is
  impossible in source too).
* `Spaghettio`(+`SpaghettiosDispenser`) — dispenser fires every 220 frames
  once seen; shot dies at 1.25 toward the player's position at spawn;
  bullet destroys it.
* `RollingRocks`(+`WatchFor`) — spawner every 200 frames; rock falls 3.75,
  lands snapped to grid, rolls ±1.875 (direction rule per source), rolls
  off ledges, dies on blockNise.
* `Playstation`(+`Kamek`) — Kamek appears in view, spawns a Playstation
  (~60 frames later), which homes at 7.5 and kills after 50 cumulative
  contact frames.
* `RoadCheep` — arcs at 7.5 launched 135°, +11.25°/6 frames once started
  (start alarms randomized 1..72 at room start); touch = knockback off the
  cart; shot → drops straight down. All despawn past x=8128.
* `RoadBulletBill` — static killers until the cart passes BulletTrigger,
  then all drift left at 1.25.
* `Eggplant` — falls 2.5, bounces between BounceDown/BounceUp markers.
* `BouncyFruit` — killer cherry launched −5, redirected to cardinal
  directions by Bounce markers.
* `Witch`(+`WitchShadow`) — shadow sweeps pWitchShadow (1082..1309 at
  0.625, ping-pong); when armed and the shadow is off every blockNise the
  witch strikes at 6.25 at her placed height; hitting blockNise → spins and
  falls 7.5. `Lonk` — 5×-scaled: paces 140..658 at 1.2625 carrying a
  rideable platform (75px wide at x−37); triggers make him slash for 12
  frames (kill on overlap, bigger mask frames 4..8).

### Platforms & vehicles
* `platform` — static one-way 32×16 platform (landing rules above).
* `movingPlatform` — creation-code velocities (±2, ±0.25...); bounces off
  solids (`stopper` stops instead), reverses h and v on blockNise; carries
  and pushes riders; view-freeze rect above. `LongForm` (long cat) is one
  with sprLongPlatform (rGuyTower instance exempt from solid bounce).
* Falling platforms: `FallingBrick` (4-frame shake → 3), `FallingFort`
  (solid until stood on → falls 2, breaks on landing), `FactoryPlatform`
  (`up` → rise −2 via yspeed, else fall 2; despawns off-view),
  `OutskirtPlatform` (fall/rise 2, breaks on landing), `metroidPlatform`
  (sinks 2 while ridden), `AscentPlatform`(+`AscentSpeedMod` pickups:
  `yspeed-=1` each) — tower ascent, `KumoPlatform` (trigger-driven ±4
  drift, returns at 1), `GuyPlatform` (loops 3 down / −1 up between
  y=1240/1792 wrap markers), `PillarMove` (platform slides x+96→x+8,
  quadratic, 60 frames), `Cart` (below), `Lonk`'s platform,
  `TheSpikeYouShoot`'s spawned platform, SpikeTrap's top.
* `Cart` — hspeed 4 +1 per CartSpeedup (20 on the road); platform 106px at
  y+4 that vanishes over DumpMoment gaps; jumping back on while falling
  re-carts; at `hspeed>5` a rider is clamped into the seat (djump=0);
  blockNise crash marker at x≈22400: player launched `hspeed=15,
  vspeed=-10, walljumpboost=-1, djump=1`, wall spawns at 22368;
  CartStopper strips (11) drop `carted`; BiggusBrickus columns of
  destructible blocks burst on contact.

### Yoku chains & tetris
* `FactoryYoku` (121) + controller: instance-order chain from the base
  block; pointer `blk` advances `blk_spd`/frame (0 → 1/100 on touching the
  controller mask, +0.28 skip; trigger zones: 1/75, 1/50, 1/25; final zone
  destroys the system). Integer crossings reveal the next block (appear
  anim −0.5); a block finishing its appear anim starts the previous one's
  disappear. Per-frame masks make un-appeared blocks non-landable.
* `RealYoku` (6, `my_id` 0..5) + controller + end trigger: started by
  TheSpikeYouShoot; every 100 frames toggles block `sequence["012345"]
  [pos++]` (event_user solid/visible toggle); end trigger solidifies all
  and stops the cycle.
* `tetrisController` (rKraidgiefLair) — fully scripted: timer −15, per-frame
  move/rotate/spawn tables (~250 events to timer≈2520), pieces are 4
  solid 32×32 tetrisBlocks re-laid per move; `create_tetrimino` freezes the
  previous piece's blocks as permanent terrain; `clear_tetris_rows` shifts
  every block down n×32 (destroy past y≥576); the pill event spawns
  KillPill (18×-scale killer falling 12.5, smashes tetrisBlocks, parks on
  solids). Compiled offline into an exact per-frame timeline of dynamic
  solids + spawns; the leave-view abort (stop + block at (763,64)) is
  runtime-conditional.

### Progression, pickups, transitions
* `deliciousFruit` (218) — static cherry killers; triggers launch them
  (`vspeed=±6.25/12.5`, one-frame activation delay per source). `CatThing`
  throws one (3.75 down) at anim frame 5.
* `warp` — per-axis semantics (already implemented); `roomTo=0` = same-room
  teleport; `code=` strings are compiled side effects (castleboost,
  factory_ceiling_flag). The factory→castle warp becomes an in-room
  teleport once `orb_dracula` is set (existing conditional lowering).
* `EntranceTele` — par=warp override: needs all six boss orbs → destroy
  player + goto rGuyRoad (start); **without them touching it kills**.
  Statues/controller are cosmetic per-orb animations.
* `BossTeleporter` ×8 — boss-room gates (justified exceptions; recorded).
* `OrbBirdo` / `OrbMother` — orb pickups in non-boss rooms (destroyed if
  flag already set): Birdo sets the flag + immediate save; Mother sets
  save-on-room-change. Modeled: flag + checkpoint at pickup.
* `secret1..6` — pickups (bob ±3, set unlock flag, despawn); trophies are
  conditional decor. `JumpRefresher` — **destroyed for the Kid**
  (`global.char!=4`) — compiled out.
* `musicChanger`, skyboxes, `deco*`, `GutsStar*`, `RoadStar`, `StaticEgg`,
  `SpinningBirdoFloor`, `SpinningFortBrick`, `WallCrack`, `PlayerSign`,
  `WonSign` (flag decor), `Bosnwentr`, `CampingNoobs`/`AndDownIGo`/
  `RunBoshy` (Boshy-only sounds, self-destruct), `ZeldaHearts`,
  `MoonBigDeco`, `MotherBrainPlatform` (no collision), `EntranceStatue*`,
  `TysonReferee`* — visual/audio only → excluded as non-gameplay.
* `MoonSmall` — triggered: falls 6, shatters destructible blocks above
  y+64 as it passes (others are static decor phases). `MoonBigFall` —
  killer moon on smooth path pMoonFall (speed 1 × per-point factors),
  smashes destructibles, goes ballistic (grav 0.4) at path end or on
  player death; force-active.
* `RoadMoon`, `Dragon`(+markers/blocks), `Tyson`(+bricks/door/star),
  `MommyThinker`, `Samus`, `TourianBarrier`'s escape context, `VicViper` +
  `Gradius*`, `Sinistar`, `ArkaBall/ArkaBrick*/ArkaPlatform`, `LuBooHoo`+
  `BowserFireClassic` chain, `GradiusBoss` — boss/secret-battle objects:
  **justified exceptions** (see coverage report); their rooms remain
  playable up to the boss trigger and all non-boss content works.
* `Ryu` — killer tatsumaki: activated (via RyuTrigger after the button):
  path pRyu at 11.25, then falls 6.25, re-path reversed at 6.25; RyuWind
  gives it −0.5 gravity; at state 4 it knocks the FactoryCeiling away
  (ceiling `solid=0` + launched). `RyuWind` region: player `vspeed-=1.5`
  per overlap frame. `Turbine`: static killer whose sprite (and precise
  mask) toggles with the button.
* `triggerLockControls` — touch: `frozen=1` (permanent; the myspace-corridor
  death gag with KillPlane).
* `TextBlock` — solid block that reveals text when shot (cosmetic text;
  solid already).
* `metroidTrap` — touch: despawn + spawn Metroid.
* `HillMove` — solid hill rises 1.875 (32px) when triggered.
* `FallingSpike10frameUp` in rGuyRoad get `spd=12.5` from a trigger.

## RNG policy

GM `irandom`/`choose`/`random_range` sites that affect gameplay:
MedusaHead/BIRD knockback, Ghoul walk duration, GhoulGenerator direction,
CheepController start alarms, save deflect direction, DestroyedSpike/
DestroyedPlatform cosmetics. The env draws these from its own seeded RNG
(deterministic per seed); the *distributions and call sites* match the
source, the GM RNG stream itself is not replicated. Recorded in the
fidelity contract.

## Known modeling notes (documented equivalences)

1. Death detection runs post-motion in the same frame; the source detects
   the same boundary overlap at the start of the next Step (same positions,
   same deaths — verified by frame tests).
2. The gameOver retry delay (~20+ frames of corpse cam) is compressed:
   respawn is immediate on the next step/attempt reset. In-life timing is
   unchanged.
3. ErrorTrap's mouse-click dismiss is not in the action space (keyboard
   game preserved).
4. Metroid latch = death 100 frames after first contact (source freezes the
   player forever; either way the attempt is over).
5. GM smooth paths (pMoonFall) are arc-length sampled offline at precision
   4; per-frame positions match GM's interpolation to sub-pixel.
6. Player hitbox corrected to the source 11×21 box (top −12) in exact
   mode; classic/legacy levels keep the historical 20-tall box.
