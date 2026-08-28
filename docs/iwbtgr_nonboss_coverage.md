# IWBTGR 1.5.3 non-boss coverage report

Generated from `build/games/iwbtgr_1_5_3.coverage.json` by
`scripts/report_exact_coverage.py`. The numbers are written by the converter at build time; an instance that matches no row here fails the build (`ConversionError`), so this table is the complete account of every placed instance in the 14 gameplay rooms.

## Summary

| category | classes | instances |
|---|---|---|
| implemented (dynamic exact-layer entities) | 143 | 2203 |
| static geometry (lowered to solids/killers at build time) | 6 | 89 |
| excluded — visual/decorative only | 52 | 263 |
| excluded — boss fight content (out of milestone scope) | 20 | 145 |
| trigger op-programs compiled | — | 135 |

Gameplay rooms: `rCastlevania`, `rFactoryOutskirts`, `rGraveyard`, `rGuy1`, `rGuyEntrance`, `rGuyFortress1`, `rGuyFortress2`, `rGuyLabyrinth`, `rGuyRoad`, `rGuyTower`, `rKraidgiefLair`, `rMegaman`, `rMetroid`, `rZelda`.

## Implemented classes

Every source object lowered to a dynamic exact-layer entity, with its placed-instance count across the gameplay rooms. Per-class source semantics (constants, timings, state machines, and which native behavior class each object lowers to) are documented in `docs/iwbtgr_nonboss_mechanics.md`.

| object | n | object | n | object | n |
|---|---|---|---|---|---|
| `blockTrapDestructible` | 249 | `BiggusBrickus` | 6 | `EggHitbox` | 1 |
| `deliciousFruit` | 218 | `CycleSpikeUp` | 6 | `EntranceTele` | 1 |
| `trigger` | 135 | `FirstRoomSpikeWall` | 6 | `FactoryCeiling` | 1 |
| `WalljumpR` | 126 | `MoonSmall` | 6 | `FactorySpinner1` | 1 |
| `FactoryYoku` | 121 | `RealYoku` | 6 | `FactorySpinner2` | 1 |
| `WalljumpL` | 100 | `yellowallR` | 6 | `FactoryYokuController` | 1 |
| `yellowallL` | 83 | `CycleSpikeDown` | 5 | `FallStair` | 1 |
| `SoftlockBlocker` | 74 | `GhoulGenerator` | 5 | `FallingBlockTrap` | 1 |
| `metroidPlatform` | 60 | `Kamek` | 5 | `FallingBrick` | 1 |
| `movingPlatform` | 51 | `LongForm` | 5 | `FlyingSpike` | 1 |
| `WeirdYellowWallR` | 50 | `metroidTrap` | 5 | `FunnySpikeMan` | 1 |
| `FirePermanent` | 49 | `spikeDown` | 5 | `Hammer` | 1 |
| `TysonBrick` | 49 | `FallingSpike10frameUp` | 4 | `HammerTrigger` | 1 |
| `WeirdYellowWallL` | 46 | `Grabby` | 4 | `Higger` | 1 |
| `FireSometimesPermanent` | 39 | `KumoPlatform` | 4 | `HillMove` | 1 |
| `FallingFort` | 36 | `ShootyBarrier` | 4 | `Lonk` | 1 |
| `FactoryPlatform` | 34 | `Skwee` | 4 | `MedusaHead` | 1 |
| `DumpMoment` | 33 | `SkweeTrigger` | 4 | `MedusaModifier` | 1 |
| `BounceDown` | 32 | `objWater2` | 4 | `OrbBirdo` | 1 |
| `BounceUp` | 32 | `FakeFallingSpike` | 3 | `OrbMother` | 1 |
| `RoadCheep` | 29 | `FireChalice` | 3 | `PillarMove` | 1 |
| `Fire` | 26 | `FireSometimesUpside` | 3 | `PlatformReset` | 1 |
| `blockNise` | 26 | `FirstRoomBarrier` | 3 | `QuickLaserTimer` | 1 |
| `FallingSpike10frame` | 21 | `FirstRoomSpike` | 3 | `RealYokuController` | 1 |
| `FireShortPermanent` | 21 | `Ghoul` | 3 | `RealYokuEndTrigger` | 1 |
| `BounceLeft` | 20 | `KumoStopper` | 3 | `Ryu` | 1 |
| `BounceRight` | 20 | `OutskirtPlatform` | 3 | `RyuButton` | 1 |
| `CartSpeedup` | 20 | `AscentSpeedMod` | 2 | `RyuWind` | 1 |
| `platform` | 20 | `BoltTrap` | 2 | `Snifit` | 1 |
| `RoadBulletBill` | 17 | `Crawler` | 2 | `SnifitCannon` | 1 |
| `SpaghettiosDispenser` | 14 | `FallingSpike` | 2 | `SniperJohn` | 1 |
| `HoverGunner` | 13 | `FireSometimes` | 2 | `SpikeTrap` | 1 |
| `GuyPlatform` | 12 | `MedusaMaker` | 2 | `TheSpikeYouShoot` | 1 |
| `CartStopper` | 11 | `PaintingTrap` | 2 | `TourianBarrier` | 1 |
| `FallingCave` | 11 | `SpikeUpExtend` | 2 | `Turbine` | 1 |
| `cameraHard` | 11 | `ZeldaFire` | 2 | `WheelTrap` | 1 |
| `TourianTurret` | 10 | `secret1` | 2 | `Witch` | 1 |
| `couchTrap` | 9 | `secret2` | 2 | `WitchShadow` | 1 |
| `BossTeleporter` | 8 | `secret3` | 2 | `ZeldaOldMan` | 1 |
| `BouncyFruit` | 8 | `secret5` | 2 | `ZeldaSword` | 1 |
| `Eggplant` | 8 | `secret6` | 2 | `cameraCart` | 1 |
| `FireOnce` | 8 | `AscentPlatform` | 1 | `cameraTower` | 1 |
| `NatsCat` | 8 | `BlownEntrance` | 1 | `secret4` | 1 |
| `FireShort` | 7 | `BulletTrigger` | 1 | `spikeUp` | 1 |
| `GraveTrap` | 7 | `Cart` | 1 | `tetrisController` | 1 |
| `QuickLaser` | 7 | `CatThing` | 1 | `trapStar` | 1 |
| `RevealingSpikesUp` | 7 | `CheepController` | 1 | `triggerLockControls` | 1 |
| `WatchFor` | 7 | `ChozoOrb` | 1 |  |  |

## Static-only classes

Objects whose source events reduce to immobile solid geometry (`solid=1`, no gameplay code beyond being stood on); the converter rasterizes their sprite masks into the static collision layers at build time.

| object | instances |
|---|---|
| blockYoku | 75 |
| blockYokuTile | 9 |
| TysonDoor | 2 |
| TextBlock | 1 |
| ZeldaCollision | 1 |
| Torizo | 1 |

## Excluded: visual/decorative

Classes whose source events contain no gameplay-relevant code (draw/animation/depth only), plus `JumpRefresher`, which the source destroys at create unless a non-default character is selected. The allowlist lives in `exact.VISUAL_CLASSES`; an object not on it cannot be excluded this way.

| object | instances |
|---|---|
| RoadStar | 59 |
| decoStar | 53 |
| GutsStarMedium | 16 |
| GutsStarLarge | 14 |
| JumpRefresher | 14 |
| kumoLeft | 12 |
| kumoRight | 12 |
| GutsStarSmall | 10 |
| musicChanger | 7 |
| decoKumoLayer | 6 |
| SpinningBirdoFloor | 6 |
| SpinningFortBrick | 5 |
| StaticEgg | 4 |
| AndDownIGo | 4 |
| FireGlow | 4 |
| GuySkybox | 1 |
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
| KraidSkybox | 1 |
| MotherBrainPlatform | 1 |
| RunBoshy | 1 |
| FactorySkybox | 1 |
| Bosnwentr | 1 |
| blockFake | 1 |
| CampingNoobs | 1 |
| CastlevaniaSkybox | 1 |
| decoKumo3 | 1 |
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

## Excluded: boss content

The milestone stops before the boss catalogue. Boss actors and the objects that only exist as part of a boss fight are excluded under `exact.BOSS_CLASSES`; the arenas themselves, their platforming approaches, and the flag-gated boss teleporters (including the defeat-flag warp conditions) are implemented.

| object | instances |
|---|---|
| ArkaBrick | 63 |
| GradiusBugz | 25 |
| ArkaBrickShort | 19 |
| DragonBlock | 15 |
| GradiusDrones | 8 |
| TysonStar | 1 |
| Tyson | 1 |
| MommyThinker | 1 |
| Samus | 1 |
| RoadMoon | 1 |
| DragonMarker | 1 |
| DragonMarker2 | 1 |
| Dragon | 1 |
| Sinistar | 1 |
| LuBooHoo | 1 |
| ArkaPlatform | 1 |
| ArkaBall | 1 |
| GradiusBoss | 1 |
| VicViper | 1 |
| GradiusMarker | 1 |

## Trigger programs targeting excluded classes

Trigger instances whose op programs reference boss/cosmetic targets compile with a recorded note (the pulse becomes a no-op at runtime until the target class exists):

- `rGuy1`: trigger 00386FA0 targets excluded class Tyson
- `rGuy1`: trigger 00120659: target TysonDoor (0018891B) is static/cosmetic
- `rMetroid`: trigger 0021871E targets excluded class MommyThinker
- `rMetroid`: trigger 000872B7 targets excluded class Samus
- `rGuyRoad`: trigger 0001A94A targets excluded class RoadMoon

## Whole-source reconciliation

Across the entire source project (boss rooms, menus, cutscene rooms included): 8212 placed instances, 4758 imported, 3454 excluded with recorded reasons (`excluded_reasons` in the JSON). Within the 14 non-boss gameplay rooms the account above is exhaustive: 2203 implemented + 89 static + 263 visual + 145 boss-content = every instance.
