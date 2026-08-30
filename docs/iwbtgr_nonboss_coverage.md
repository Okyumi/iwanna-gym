# IWBTGR 1.5.3 non-boss coverage report

Generated from `build/games/iwbtgr_1_5_3.coverage.json` by
`scripts/report_exact_coverage.py`. The numbers are written by the converter at build time; an instance that matches no row here fails the build (`ConversionError`), so this table is the complete account of every placed instance in the 14 gameplay rooms.

## Summary

| category | classes | instances |
|---|---|---|
| implemented (dynamic exact-layer entities) | 164 | 2419 |
| static geometry (lowered to solids/killers at build time) | 5 | 87 |
| excluded — visual/decorative only | 70 | 340 |
| excluded — boss fight content (out of milestone scope) | 0 | 0 |
| trigger op-programs compiled | — | 137 |

Gameplay rooms: `rCastlevania`, `rFactoryOutskirts`, `rGraveyard`, `rGuy1`, `rGuyEntrance`, `rGuyFortress1`, `rGuyFortress2`, `rGuyLabyrinth`, `rGuyRoad`, `rGuyTower`, `rKraidgiefLair`, `rMegaman`, `rMetroid`, `rZelda`.

## Implemented classes

Every source object lowered to a dynamic exact-layer entity, with its placed-instance count across the gameplay rooms. Per-class source semantics (constants, timings, state machines, and which native behavior class each object lowers to) are documented in `docs/iwbtgr_nonboss_mechanics.md`.

| object | n | object | n | object | n |
|---|---|---|---|---|---|
| `blockTrapDestructible` | 249 | `BiggusBrickus` | 6 | `EntranceTele` | 1 |
| `deliciousFruit` | 218 | `CycleSpikeUp` | 6 | `FactoryCeiling` | 1 |
| `trigger` | 135 | `FirstRoomSpikeWall` | 6 | `FactorySpinner1` | 1 |
| `WalljumpR` | 126 | `MoonSmall` | 6 | `FactorySpinner2` | 1 |
| `FactoryYoku` | 121 | `RealYoku` | 6 | `FactoryYokuController` | 1 |
| `WalljumpL` | 100 | `yellowallR` | 6 | `FallStair` | 1 |
| `yellowallL` | 83 | `CycleSpikeDown` | 5 | `FallingBlockTrap` | 1 |
| `SoftlockBlocker` | 74 | `GhoulGenerator` | 5 | `FallingBrick` | 1 |
| `ArkaBrick` | 63 | `Kamek` | 5 | `FlyingSpike` | 1 |
| `metroidPlatform` | 60 | `LongForm` | 5 | `FunnySpikeMan` | 1 |
| `movingPlatform` | 51 | `metroidTrap` | 5 | `GradiusBoss` | 1 |
| `WeirdYellowWallR` | 50 | `FallingSpike10frameUp` | 4 | `GradiusMarker` | 1 |
| `FirePermanent` | 49 | `Grabby` | 4 | `Hammer` | 1 |
| `TysonBrick` | 49 | `KumoPlatform` | 4 | `HammerTrigger` | 1 |
| `WeirdYellowWallL` | 46 | `ShootyBarrier` | 4 | `Higger` | 1 |
| `spikeUp` | 46 | `Skwee` | 4 | `HillMove` | 1 |
| `FireSometimesPermanent` | 39 | `SkweeTrigger` | 4 | `Lonk` | 1 |
| `FallingFort` | 36 | `objWater2` | 4 | `LuBooHoo` | 1 |
| `FactoryPlatform` | 34 | `spikeRight` | 4 | `MedusaHead` | 1 |
| `DumpMoment` | 33 | `FakeFallingSpike` | 3 | `MedusaModifier` | 1 |
| `BounceDown` | 32 | `FireChalice` | 3 | `MommyThinker` | 1 |
| `BounceUp` | 32 | `FireSometimesUpside` | 3 | `OrbBirdo` | 1 |
| `RoadCheep` | 29 | `FirstRoomBarrier` | 3 | `OrbMother` | 1 |
| `blockNise` | 28 | `FirstRoomSpike` | 3 | `PillarMove` | 1 |
| `Fire` | 26 | `Ghoul` | 3 | `PlatformReset` | 1 |
| `GradiusBugz` | 25 | `KumoStopper` | 3 | `QuickLaserTimer` | 1 |
| `spikeDown` | 23 | `OutskirtPlatform` | 3 | `RealYokuController` | 1 |
| `FallingSpike10frame` | 21 | `AscentSpeedMod` | 2 | `RealYokuEndTrigger` | 1 |
| `FireShortPermanent` | 21 | `BoltTrap` | 2 | `RoadMoon` | 1 |
| `BounceLeft` | 20 | `Crawler` | 2 | `Ryu` | 1 |
| `BounceRight` | 20 | `FallingSpike` | 2 | `RyuButton` | 1 |
| `CartSpeedup` | 20 | `FireSometimes` | 2 | `RyuWind` | 1 |
| `platform` | 20 | `MedusaMaker` | 2 | `Sinistar` | 1 |
| `ArkaBrickShort` | 19 | `PaintingTrap` | 2 | `Snifit` | 1 |
| `RoadBulletBill` | 17 | `SpikeUpExtend` | 2 | `SnifitCannon` | 1 |
| `DragonBlock` | 15 | `TysonDoor` | 2 | `SniperJohn` | 1 |
| `SpaghettiosDispenser` | 14 | `ZeldaFire` | 2 | `SpikeTrap` | 1 |
| `HoverGunner` | 13 | `secret1` | 2 | `TheSpikeYouShoot` | 1 |
| `GuyPlatform` | 12 | `secret2` | 2 | `TourianBarrier` | 1 |
| `cameraHard` | 12 | `secret3` | 2 | `Turbine` | 1 |
| `CartStopper` | 11 | `secret5` | 2 | `Tyson` | 1 |
| `FallingCave` | 11 | `secret6` | 2 | `VicViper` | 1 |
| `TourianTurret` | 10 | `ArkaBall` | 1 | `WheelTrap` | 1 |
| `couchTrap` | 9 | `ArkaPlatform` | 1 | `Witch` | 1 |
| `BossTeleporter` | 8 | `AscentPlatform` | 1 | `WitchShadow` | 1 |
| `BouncyFruit` | 8 | `BlownEntrance` | 1 | `ZeldaOldMan` | 1 |
| `Eggplant` | 8 | `BulletTrigger` | 1 | `ZeldaSword` | 1 |
| `FireOnce` | 8 | `Cart` | 1 | `cameraCart` | 1 |
| `GradiusDrones` | 8 | `CatThing` | 1 | `cameraKraid` | 1 |
| `NatsCat` | 8 | `CheepController` | 1 | `cameraTower` | 1 |
| `FireShort` | 7 | `ChozoOrb` | 1 | `secret4` | 1 |
| `GraveTrap` | 7 | `Dragon` | 1 | `tetrisController` | 1 |
| `QuickLaser` | 7 | `DragonMarker` | 1 | `trapStar` | 1 |
| `RevealingSpikesUp` | 7 | `DragonMarker2` | 1 | `triggerLockControls` | 1 |
| `WatchFor` | 7 | `EggHitbox` | 1 |  |  |

## Static-only classes

Objects whose source events reduce to immobile solid geometry (`solid=1`, no gameplay code beyond being stood on); the converter rasterizes their sprite masks into the static collision layers at build time.

| object | instances |
|---|---|
| blockYoku | 75 |
| blockYokuTile | 9 |
| TextBlock | 1 |
| ZeldaCollision | 1 |
| Torizo | 1 |

## Excluded: visual/decorative

Classes whose source events contain no gameplay-relevant code (draw/animation/depth only), plus `JumpRefresher`, which the source destroys at create unless a non-default character is selected. The allowlist lives in `exact.VISUAL_CLASSES`; an object not on it cannot be excluded this way.

| object | instances |
|---|---|
| decoStar | 107 |
| RoadStar | 59 |
| GutsStarMedium | 16 |
| JumpRefresher | 15 |
| GutsStarLarge | 14 |
| kumoLeft | 12 |
| kumoRight | 12 |
| GutsStarSmall | 10 |
| decoKumoLayer | 8 |
| musicChanger | 7 |
| SpinningBirdoFloor | 6 |
| SpinningFortBrick | 5 |
| StaticEgg | 4 |
| AndDownIGo | 4 |
| FireGlow | 4 |
| decoKumo3 | 2 |
| DeadGuyBrow | 2 |
| GuySkybox | 1 |
| TysonStar | 1 |
| decoGameover | 1 |
| MoonBigDeco | 1 |
| TysonReferee | 1 |
| secret4trophy | 1 |
| secret1trophy | 1 |
| secret2trophy | 1 |
| secret3trophy | 1 |
| secret5trophy | 1 |
| secret6trophy | 1 |
| BossTeleporter.dev | 1 |
| PlayerSign | 1 |
| ZeldaHearts | 1 |
| GraveyardSkybox | 1 |
| MechaWarning | 1 |
| KraidSkybox | 1 |
| MotherBrainPlatform | 1 |
| Samus | 1 |
| RunBoshy | 1 |
| FactorySkybox | 1 |
| Bosnwentr | 1 |
| blockFake | 1 |
| CampingNoobs | 1 |
| CastlevaniaSkybox | 1 |
| EntranceStatue6 | 1 |
| EntranceStatue5 | 1 |
| EntranceStatue4 | 1 |
| EntranceStatue3 | 1 |
| EntranceStatue2 | 1 |
| EntranceStatue1 | 1 |
| EntranceController | 1 |
| RoadSkybox | 1 |
| RoadSkybox2 | 1 |
| RoadSkybox3 | 1 |
| FortressSkybox | 1 |
| WallCrack | 1 |
| WonSign | 1 |
| saveVeryEvil | 1 |
| GlAsshole | 1 |
| Glass1 | 1 |
| Glass2 | 1 |
| Glass3 | 1 |
| Glass4 | 1 |
| Glass5 | 1 |
| GuyDarkness | 1 |
| EndingSkybox | 1 |
| DeadGuy | 1 |
| DeadGuyMouth | 1 |
| EndingKid1 | 1 |
| EndingGun1 | 1 |
| EndingKid2 | 1 |
| EndingSkybox2 | 1 |

## Excluded: boss content

Since the full-game milestone every boss is implemented, so this bucket is empty; it remains a build gate — any placed boss-class instance that loses its implementation lands here and fails coverage. See [iwbtgr_boss_coverage.md](iwbtgr_boss_coverage.md) for the boss catalogue.

| object | instances |
|---|---|

## Trigger programs targeting excluded classes

Trigger instances whose op programs reference boss/cosmetic targets compile with a recorded note (the pulse becomes a no-op at runtime until the target class exists):

- `rMetroid`: trigger 000872B7 targets excluded class Samus

## Whole-source reconciliation

Across the entire source project (boss rooms, menus, cutscene rooms included): 8212 placed instances, 4758 imported, 3454 excluded with recorded reasons (`excluded_reasons` in the JSON). Within the 14 non-boss gameplay rooms the account above is exhaustive: 2419 implemented + 87 static + 340 visual + 0 boss-content = every instance.
