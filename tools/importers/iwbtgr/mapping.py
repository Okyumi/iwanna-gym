"""Semantic classification of IWBTGR source objects.

Every source object is classified into a semantic type with one of five
statuses (docs/iwbtgr_object_mapping.md):

* ``exact``            — current runtime represents it with identical semantics
* ``equivalent``       — representable now with a documented difference
* ``unsupported``      — gameplay-relevant, needs work (GML port/lowering)
* ``irrelevant``       — menu/meta/dev content, not part of gameplay import
* ``visual_audio_only``— no gameplay effect (decoration, particles, music)

Classification is fully mechanical and reproducible: an explicit table
first, then family rules (name patterns), then room-usage and property
heuristics, then parent-chain inheritance. Anything left over defaults to
``unsupported`` — the pipeline never guesses an object into the game.
Each result records which rule fired (``rule``) so the tables can be
audited. Nothing here is derived from screenshots or memory; inputs are
the parsed source properties, events, and placements only.
"""
from __future__ import annotations

import re
from typing import Any

MENU_ROOMS = {"rInit", "rTitle", "rFiles", "rUnlocks", "rCredits"}
SECONDARY_ROOMS = {"rBossRush", "rDev"}
STATUSES = ("exact", "equivalent", "unsupported", "irrelevant",
            "visual_audio_only")

#: explicit mappings for identified core objects: name -> (semantic, status, notes)
EXPLICIT: dict[str, tuple[str, str, str]] = {
    # --- player / spawn / death ---
    "player":       ("player", "equivalent",
                     "Yuuutu-family player (mask sprMask); constants must be "
                     "diffed against the C core before any physics-exact claim"),
    "playerStart":  ("player_spawn", "exact", "spawn marker"),
    "playerKiller": ("killer_parent", "equivalent",
                     "parent class of deadly objects; maps to EF_DEADLY"),
    "KillPill":     ("killer", "equivalent", ""),
    "KillPlane":    ("killer_region", "equivalent", "kill zone (autoscroller)"),
    # --- solids ---
    "block":        ("solid_block", "exact", "32x32 invisible solid over tiles"),
    "blockMini":    ("solid_block_small", "equivalent", "sub-tile solid; runtime "
                     "tile grid is 32px — needs sub-tile solids or mask entity"),
    "blockNotMerge": ("solid_block", "equivalent", "non-merging solid variant"),
    "blockNise":    ("solid_block", "equivalent", "variant solid"),
    "blockPlatform": ("platform_solid", "equivalent", ""),
    "blockKill":    ("killer_block", "equivalent", "solid that kills on touch"),
    "blockFake":    ("fake_block", "visual_audio_only",
                     "looks solid, has no collision (gag block)"),
    "blockPush":    ("pushable_block", "unsupported", "pushable physics object"),
    "blockLift":    ("moving_solid", "unsupported", "moving solid (lift)"),
    "blockTrapDestructible": ("destructible_block", "unsupported",
                              "destroyed by player gun / events"),
    "blockYoku":    ("yoku_block", "unsupported", "timed appear/disappear solid"),
    "blockYokuTile": ("yoku_block", "unsupported", ""),
    "RealYoku":     ("yoku_block", "unsupported", ""),
    "FactoryYoku":  ("yoku_block", "unsupported", ""),
    # --- spikes ---
    "spikeUp":      ("spike_up", "exact", "standard triangular mask"),
    "spikeDown":    ("spike_down", "exact", ""),
    "spikeLeft":    ("spike_left", "exact", ""),
    "spikeRight":   ("spike_right", "exact", ""),
    # --- saves / warps / triggers / progression ---
    "saveMedium":   ("save_point", "equivalent",
                     "difficulty-gated save (Medium+); difficulty variants "
                     "not yet in runtime"),
    "saveHard":     ("save_point", "equivalent", "Hard+ save"),
    "saveVeryHard": ("save_point", "equivalent", "Very Hard save (parent of others)"),
    "saveBoshy":    ("save_point", "equivalent", "special save variant"),
    "saveVeryEvil": ("save_point", "equivalent", "special save variant"),
    "warp":         ("warp", "equivalent",
                     "teleport/room transition; creation code carries target"),
    "trigger":      ("trigger_region", "equivalent",
                     "generic trigger; attached creation code decides effect — "
                     "each placement classified at conversion time"),
    "triggerLockControls": ("trigger_scripted", "unsupported", "cutscene control lock"),
    "SoftlockBlocker": ("barrier", "equivalent", "one-way anti-softlock solid"),
    "musicChanger": ("audio_control", "visual_audio_only", ""),
    "TheGun":       ("item_gun", "unsupported",
                     "grants shooting — changes the action space"),
    "JumpRefresher": ("jump_refresher", "unsupported", "restores air jump on touch"),
    "objWater":     ("water", "unsupported", "swim physics region"),
    "objWater2":    ("water", "unsupported", "water variant (infinite jump)"),
    "WalljumpL":    ("walljump_wall", "unsupported", "walljump mechanic absent"),
    "WalljumpR":    ("walljump_wall", "unsupported", ""),
    "yellowallL":   ("walljump_wall", "unsupported", ""),
    "yellowallR":   ("walljump_wall", "unsupported", ""),
    "WeirdYellowWallL": ("walljump_wall", "unsupported", ""),
    "WeirdYellowWallR": ("walljump_wall", "unsupported", ""),
    # --- common hazards / movers ---
    "deliciousFruit": ("fruit_hazard", "equivalent",
                       "classic cherry; static or launched by triggers"),
    "BouncyFruit":  ("fruit_hazard", "unsupported", "bouncing behavior"),
    "movingPlatform": ("moving_platform", "equivalent", ""),
    "platform":     ("platform", "equivalent", "jump-through platform parent"),
    "bullet":       ("projectile", "equivalent", ""),
    "Fire":         ("triggered_hazard", "unsupported",
                     "classic fire trap; candidate lowering to trigger+launch, "
                     "verify GML at conversion"),
    "Grenade":      ("projectile", "unsupported", "arcing grenade"),
    "SpikeTrap":    ("trap_spike", "equivalent", "launched trap spike"),
    "FallingSpike": ("trap_spike", "equivalent", "falls when triggered"),
    "FakeFallingSpike": ("trap_spike", "equivalent", "gag variant"),
    "FlyingSpike":  ("moving_hazard", "unsupported", ""),
    "MedusaHead":   ("enemy", "unsupported", "sine-wave flyer"),
    "Thwomp":       ("enemy", "unsupported", ""),
    "cameraSmooth": ("camera_control", "unsupported",
                     "view control; relevant where kill planes follow the view"),
    "cameraHard":   ("camera_control", "unsupported", ""),
    "cameraKraid":  ("camera_control", "unsupported", ""),
    "cameraTower":  ("camera_control", "unsupported", "autoscroller camera"),
    "cameraCart":   ("camera_control", "unsupported", ""),
    "ViewMover":    ("camera_control", "unsupported", ""),
    "world":        ("game_controller", "irrelevant",
                     "global controller (settings, pause, save I/O)"),
    "PauseMenu":    ("menu_meta", "irrelevant", ""),
    "gameOver":     ("menu_meta", "irrelevant", ""),
    "LanguageSwitcher": ("menu_meta", "irrelevant", ""),
    "UnlockPrompt": ("menu_meta", "irrelevant", ""),
    "hitboxMeasure": ("dev_tool", "irrelevant", ""),
    "WatchFor":     ("dev_tool", "irrelevant", ""),
    "BossRushController": ("bossrush_meta", "irrelevant",
                           "Boss Rush mode controller (secondary mode)"),
    "RushTeleporter": ("bossrush_meta", "irrelevant", ""),
    "BossTeleporter": ("bossrush_meta", "irrelevant", ""),
    "EndingController": ("ending_meta", "unsupported",
                         "ending sequence control (completion condition)"),
}

#: (regex, semantic, status, notes) — first match wins, applied after EXPLICIT
FAMILIES: list[tuple[str, str, str, str]] = [
    (r"^Credits", "credits", "irrelevant", "credits sequence"),
    (r"^Title", "menu_meta", "irrelevant", "title screen"),
    (r"^Files|^Opts", "menu_meta", "irrelevant", "file select / options"),
    (r"^Ending", "ending_meta", "unsupported", "ending sequence"),
    (r"^Orb", "progression_orb", "unsupported",
     "boss-clear orb: sets a global progression flag (flag itself maps to "
     "runtime gflags; pickup behavior needs lowering)"),
    (r"^secret\d(trophy)?$", "secret_item", "unsupported",
     "secret collectible (progression-adjacent)"),
    (r"Skybox|^deco|^Moon|^kumo|^Kumo|Painting|^part|^blood$|^bloodEmitter$"
     r"|^gibParticle$|^BoshyBlood$|^OwataBlood$|^VicBlood$|^EctoParticle$"
     r"|^MagicSmoke$|^FireGlow$|^DracMoon$|^etex$|^WonSign$|^TextBlock$"
     r"|^LongForm$|^DeadGuy|^Playstation$|^Poggers$|^NatsCat$|^MONKY$"
     r"|^CatThing$|^Skwee$|^CampingNoobs$|^FunnySpikeMan$|^GlAsshole$"
     r"|^Spaghettio", "decoration", "visual_audio_only",
     "decorative / particle / gag object"),
    (r"^(Tyson|MechaBirdo|Mecha|Birdo|Kraidgief|KG|Bowser|Drac|Dracula"
     r"|Dragon|GutsMan|Guts|GradiusBoss|Guy(First|Head|Mouth|brow|Tooth"
     r"|Shot|SpreadBullet|BouncingBullet|GlassShot|Darkness"
     r"|PersistentFirePillar)|Wily|Torizo|MommyThinker|Metroid$|Samus"
     r"|Sinistar|VicViper|VicBullet|VicDeader|Witch|Wart|Kamek|Tetris"
     r"|tetri|Egg|StaticEgg)", "boss_or_boss_part", "unsupported",
     "boss AI / boss-fight component; requires GML port"),
    (r"^(BIRD|FlyGuy|Crawler|Spider|Snifit|Ghoul|Gastly|Grabby|HoverGun"
     r"|HoverShot|RoadBulletBill|RoadCheep|Cheep|PokeyBall|Lonk|LuBooHoo"
     r"|Higger|Blanka|Ryu$|RyuWind|RunBoshy|SniperJohn|Unit$|Turbine"
     r"|Hammer$|MedusaFlame|Geye|DumbBugz|DeadBugz|GradiusBugz)", "enemy",
     "unsupported", "enemy with bespoke GML behavior"),
    (r"(Trigger|trigger)$", "trigger_scripted", "unsupported",
     "specialized trigger driving scripted sequences"),
    (r"^(Falling|Rolling|Wheel|Grave|couch|Bolt|Painting|RenkoPainting"
     r"|Error|trapStar|PaintingTrap)", "trap", "unsupported",
     "scripted trap; candidate for event-system lowering at conversion"),
    (r"^(CycleSpike|RevealingSpikes|SpikeUpExtend|FirstRoomSpike"
     r"|TheSpikeYouShoot)", "cycling_spike", "unsupported",
     "timed/scripted spike variant"),
    (r"Platform$|^FallStair$|^AscentPlatform$", "platform", "equivalent",
     "jump-through platform family"),
    (r"^(Cart|CartStopper|CartSpeedup)$", "vehicle_section", "unsupported",
     "trolley section"),
    (r"Controller$|Maker$|Modifier$|Spawner$|Generator$|Reset$|SpeedMod$"
     r"|Ctrl$|^QuickLaserTimer$|^MedusaMaker$", "controller_spawner",
     "unsupported", "room controller / spawner logic"),
    (r"Barrier$", "barrier", "equivalent", "solid barrier variant"),
    (r"^(Glass\d|DracGlass|WallCrack|BlownEntrance|Bosnwentr|DestroyedBlock"
     r"|DestroyedPlatform|DestroyedSpike|SpaghettioDestroyed|SnifitDead"
     r"|MedusaDead|Deadcula)$", "breakable_state", "unsupported",
     "breakable / post-destruction state object"),
    (r"^(Zelda|Entrance|Factory|Fortress|Graveyard|Kraid|Road|Castlevania"
     r"|Tourian|Owata|Gradius|Ascent|Outskirt|Hill|Pillar|Mother"
     r"|Spinning)", "zone_object", "unsupported",
     "zone-specific scripted object; classify precisely at conversion"),
    (r"^Fire", "triggered_hazard", "unsupported", "fire-trap variant"),
    (r"^(bigexp|.*[Ee]xplosion|.*Splosion|.*BOOM.*|NinjaExplosion)$",
     "effect", "visual_audio_only", "explosion/effect"),
]

_FAMILY_RES = [(re.compile(p), s, st, n) for p, s, st, n in FAMILIES]


def classify_object(name: str, obj: Any, project: Any,
                    rooms_used: set[str], mod_added: bool) -> dict[str, Any]:
    """Return {"semantic", "status", "notes", "rule"} for one source object."""
    if mod_added:
        return {"semantic": "autosplitter_mod", "status": "irrelevant",
                "notes": "added/modified by the autosplitter mod, not part of "
                         "IWBTGR 1.5.3 gameplay", "rule": "mod_delta"}
    if name in EXPLICIT:
        s, st, n = EXPLICIT[name]
        return {"semantic": s, "status": st, "notes": n, "rule": "explicit"}
    for rx, s, st, n in _FAMILY_RES:
        if rx.search(name):
            return {"semantic": s, "status": st, "notes": n,
                    "rule": f"family:{rx.pattern[:32]}"}
    # usage-based: appears only in menu/meta rooms
    if rooms_used and rooms_used <= (MENU_ROOMS | SECONDARY_ROOMS):
        return {"semantic": "menu_meta", "status": "irrelevant",
                "notes": f"placed only in non-gameplay rooms {sorted(rooms_used)}",
                "rule": "rooms_usage"}
    # parent chain inheritance
    for parent in project.parent_chain(name):
        if parent in EXPLICIT:
            s, st, n = EXPLICIT[parent]
            return {"semantic": s, "status": st,
                    "notes": f"inherited from parent {parent}: {n}".strip(),
                    "rule": f"parent:{parent}"}
    # property heuristic: visible sprite, no solid, no events -> decoration
    if obj is not None and not obj.solid and not obj.events and obj.visible:
        return {"semantic": "decoration", "status": "visual_audio_only",
                "notes": "visible, non-solid, no events", "rule": "props:inert"}
    if obj is not None and obj.solid and not obj.events:
        return {"semantic": "solid_block", "status": "equivalent",
                "notes": "solid with no events (collision geometry)",
                "rule": "props:solid"}
    return {"semantic": "unclassified", "status": "unsupported",
            "notes": "not classified by any rule; needs GML review — never "
                     "guessed into the game", "rule": "default"}
