"""Boss conversion for iwbtgr_1_5_3 — the full boss catalogue.

Emits the exact-layer content of every boss and boss-linked sequence in
the game: the dedicated arenas (rMechaBirdoBoss, rKraidgiefBoss,
rDraculaBoss, rBowserBoss, rGuyBoss and the rEnding completion room) and
the bosses embedded in gameplay rooms (Tyson in rGuy1, the Mother-Brain
escape in rMetroid, RoadMoon/Dragon/Gradius segment in rGuyRoad, the
Arkanoid + Sinistar set in rGuyFortress2).  The same coverage gates
apply throughout; behavior constants live in c_src/boss/*.h with the
source files cited there and in docs/boss_architecture.md.
"""
from __future__ import annotations

import math

#: rooms converted by this module (in addition to exact.GAMEPLAY_ROOMS)
BOSS_ROOMS = ["rMechaBirdoBoss", "rKraidgiefBoss", "rDraculaBoss",
              "rBowserBoss", "rGuyBoss", "rEnding"]

#: reaching this room is full-game completion (room record kind 1)
ENDING_ROOM = "rEnding"

#: Kraidgief body sprites, indexed by the C-side KGS_* enum
KG_SPRITES = [
    "sprKraidgiefWalk", "sprKraidgiefChop", "sprKraidgiefPunch",
    "sprKraidgiefLariet", "sprKraidgiefChargeUp", "sprKraidgiefHeadbutt",
    "sprKraidgiefAngryStand", "sprKraidgiefFire", "sprKraidgiefGrab",
    "sprKraidgiefSPD", "sprKraidgiefShit", "sprKraidgiefDying",
]


def _path_keys(build, name):
    """Sample a GM path to equal-arc keys:
    [total_len, n, x0,y0,sp0, x1,y1,sp1, ...] where sp is the GM
    per-point speed percentage / 100 (path_speed multiplier),
    interpolated along the arc like the position."""
    key = ("pathkeys", name)
    if key in build._tmpl_key:
        return build._tmpl_key[key]
    from .exact import _load_path, _path_polyline
    p = _load_path(build.source_root, name)
    poly = _path_polyline(p["points"], p["smooth"], p["closed"])
    pts = [(x, y) for x, y, _sp in poly]
    sps = [sp / 100.0 for _x, _y, sp in poly]
    seg = [0.0]
    for a, b in zip(pts, pts[1:]):
        seg.append(seg[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = seg[-1] if seg[-1] > 0 else 1.0
    n = 129
    out = [total, float(n)]
    j = 0
    for i in range(n):
        s = total * i / (n - 1)
        while j < len(seg) - 2 and seg[j + 1] < s:
            j += 1
        span = seg[j + 1] - seg[j]
        f = (s - seg[j]) / span if span > 0 else 0.0
        out.append(pts[j][0] + (pts[j + 1][0] - pts[j][0]) * f)
        out.append(pts[j][1] + (pts[j + 1][1] - pts[j][1]) * f)
        out.append(sps[j] + (sps[j + 1] - sps[j]) * f)
    off, _n = build.add_keys(out)
    build._tmpl_key[key] = off
    return off


def template_for(build, cls_name):
    """Boss-family runtime-spawn templates (None: not a boss class)."""
    from . import exact as X
    M = build.mask
    T = build.template
    K = X.XEF_KILLER
    if cls_name == "MechaEgg":
        return T("XB_MECHAEGG", M("sprEgg"), key=("MechaEgg",))
    if cls_name == "EggPlatform":
        return T("XB_EGGPLAT", M("sprDynamicPlatform01"), xs=137.0 / 32.0,
                 flags=X.XEF_PLATFORM, key=("EggPlatform",))
    if cls_name == "EggHitbox":
        return T("XB_EGGHITBOX", M("sprEggHitbox"), flags=K,
                 key=("EggHitbox",))
    if cls_name == "BirdoLaza":
        return T("XB_LAZA", M("sprLaza"), flags=K, key=("BirdoLaza",))
    if cls_name == "FlyGuy":
        return T("XB_FLYGUY", M("sprFlyGuy"), xs=-2.0, ys=2.0,
                 flags=X.XEF_SHOOTABLE, key=("FlyGuy",))
    if cls_name == "KGHadouken":
        return T("XB_KGPROJ", M("sprKGHadouken"), flags=K,
                 key=("KGHadouken",))
    if cls_name == "KGFireDown":
        return T("XB_KGFIRE", M("sprKGFireDown"), xs=4.75, ys=4.75,
                 flags=K, key=("KGFireDown",))
    if cls_name == "KGFireSide":
        return T("XB_KGFIRE", M("sprKGFireSide"), xs=5.5, ys=5.5,
                 flags=K, key=("KGFireSide",))
    if cls_name == "KraidgiefDebris":
        return T("XB_KGDEBRIS", M("sprKraidgiefDebris"),
                 key=("KGDebris",))
    if cls_name == "KraidgiefDebrisSpawner":
        return T("XB_KGDEBRISSPAWN", 0xffff,
                 p=[template_for(build, "KraidgiefDebris")],
                 key=("KGDebrisSpawner",))
    if cls_name == "Blanka":
        return T("XB_BLANKA", M("sprBlanka"), flags=X.XEF_SOLID,
                 p=[M("sprBlankaHitbox"),
                    template_for(build, "KraidgiefDebrisSpawner")],
                 key=("Blanka",))
    if cls_name == "Kraidgief":
        keys_off, _ = build.add_keys([M(s) for s in KG_SPRITES])
        return T("XB_BOSS_KRAIDGIEF", M("sprKraidgiefWalk"),
                 xs=5.5, ys=5.5, flags=K | X.XEF_FORCE_ACTIVE,
                 p=[_weak_template(build, M("sprKraidgiefHitbox"),
                                   key=("wpKG",)),
                    _weak_template(build, M("sprKraidgiefEyebox"),
                                   key=("wpKGEye",)),
                    template_for(build, "KGHadouken"),
                    template_for(build, "KGFireDown"),
                    template_for(build, "KGFireSide"),
                    template_for(build, "Blanka"),
                    template_for(build, "KraidgiefDebrisSpawner"),
                    keys_off],
                 key=("Kraidgief",))
    # ---- Tyson ----
    if cls_name == "TysonFireball":
        return T("XB_TYSONFIREBALL", M("sprMask"), flags=K,
                 key=("TysonFireball",))
    if cls_name == "OrbTyson":
        return T("XB_ORB", M("sprUnit"),
                 p=[X.PROGRESSION_FLAGS["orb_tyson"]], key=("OrbTyson",))
    # ---- Dracula ----
    if cls_name == "DracTele":
        return T("XB_DRACTELE", 0xffff, key=("DracTele",))
    if cls_name == "DracGlass":
        return T("XB_DRACGLASS", M("sprDraculaGlass"), xs=3.0, ys=3.0,
                 flags=K, key=("DracGlass",))
    if cls_name == "DracApple":
        return T("XB_DRACPROJ", M("sprCherry"), flags=K,
                 key=("DracApple",))
    if cls_name == "DracMoon":
        return T("XB_DRACPROJ", M("sprMoonBig"),
                 xs=142.0 / 228.0 * 3, ys=142.0 / 228.0 * 3, flags=K,
                 key=("DracMoon",))
    if cls_name == "DracOrbiter":
        return T("XB_DRACPROJ", M("sprOrbiter"), flags=K,
                 key=("DracOrbiter",))
    if cls_name == "WilyFirePillar":
        return T("XB_WILYPILLAR", M("sprWilyFirePillar"), xs=2.0, ys=2.0,
                 flags=K, key=("WilyFirePillar",))
    if cls_name == "DracFireball":
        return T("XB_DRACFIREBALL", M("sprWilyFireball"), xs=2.0, ys=2.0,
                 flags=K, p=[template_for(build, "WilyFirePillar")],
                 key=("DracFireball",))
    if cls_name == "DracDeathSpiral":
        return T("XB_DRACSPIRAL", M("sprDraculaDeathSpiral"), flags=K,
                 p=[0, template_for(build, "DracApple")],
                 key=("DracDeathSpiral",))
    if cls_name == "DractoPlasm":
        return T("XB_DRACPLASM", M("sprEctoplasm"), xs=2.0, ys=2.0,
                 flags=K,
                 p=[1.0, template_for(build, "DracTele")],
                 key=("DractoPlasm",))
    if cls_name == "OrbDracula":
        # source OrbDracula Alarm_0 (alarm[0] = 50*3.7 = 185f after
        # pickup): player to (3040,960) + room_goto(rFactoryOutskirts) —
        # the boss room has no other exit
        return T("XB_ORB", M("sprUnit"),
                 p=[X.PROGRESSION_FLAGS["orb_dracula"],
                    build.room_index["rFactoryOutskirts"] + 1,
                    3040.0, 960.0, 185.0],
                 key=("OrbDracula",))
    if cls_name == "Deadcula":
        return T("XB_BOSS_DEADCULA", M("sprDracula"), xs=3.0, ys=3.0,
                 p=[template_for(build, "OrbDracula"),
                    template_for(build, "DracTele"),
                    M("sprDraculasTrueForm")],   # state-3 shootable mask
                 key=("Deadcula",))
    if cls_name == "Dracula":
        return T("XB_BOSS_DRACULA", M("sprDracula"), xs=3.0, ys=3.0,
                 flags=X.XEF_FORCE_ACTIVE,
                 p=[template_for(build, "DracTele"),
                    template_for(build, "DracApple"),
                    template_for(build, "DracMoon"),
                    template_for(build, "DracOrbiter"),
                    template_for(build, "DracFireball"),
                    template_for(build, "DracDeathSpiral"),
                    template_for(build, "DractoPlasm"),
                    template_for(build, "Deadcula"),
                    _weak_template(build, M("sprDraculasFace"),
                                   key=("wpDracFace",))],
                 key=("Dracula",))
    # ---- Bowser / Wart / Wily ----
    if cls_name == "BowserExplosion":
        return T("XB_BOWSEREXPL", M("sprBowserExplosion"), xs=7.0, ys=7.0,
                 flags=K, key=("BowserExplosion",))
    if cls_name == "BowserBomb":
        return T("XB_BOWSERBOMB", M("sprBowserBomb"), xs=3.0, ys=3.0,
                 flags=K, p=[template_for(build, "BowserExplosion")],
                 key=("BowserBomb",))
    if cls_name == "BowserFireClassic":
        return T("XB_BOWSERFIRE", M("sprBowserFireClassic"), xs=5.0,
                 ys=5.0, flags=K | X.XEF_FORCE_ACTIVE,
                 key=("BowserFireClassic",))
    if cls_name == "WartBanzai":
        return T("XB_WARTBANZAI", M("sprWartBanzai"), xs=3.0, ys=3.0,
                 flags=K, p=[template_for(build, "BowserExplosion")],
                 key=("WartBanzai",))
    if cls_name == "WartPoof":
        return T("XB_WARTPOOF", M("sprWartPoofRight"), flags=K,
                 key=("WartPoof",))
    if cls_name == "WilyBall":
        return T("XB_WILYBALL", M("sprWilyBall"), xs=3.0, ys=3.0,
                 flags=K, key=("WilyBall",))
    if cls_name == "WilyFireball":
        return T("XB_WILYFIREBALL", M("sprWilyFireball"), xs=2.0, ys=2.0,
                 flags=K, p=[template_for(build, "WilyFirePillar")],
                 key=("WilyFireball",))
    if cls_name == "OrbBowser":
        return T("XB_ORB", M("sprUnit"),
                 p=[X.PROGRESSION_FLAGS["orb_bowser"]], key=("OrbBowser",))
    if cls_name == "BowserFloor":
        return T("XB_BOWSERFLOOR", M("sprBowserFloor"),
                 flags=X.XEF_SOLID, key=("BowserFloor",))
    if cls_name == "FallingCeilingWall":
        return T("XB_KGCEIL", M("sprFallingCeilingWall"),
                 flags=X.XEF_SOLID, key=("FCWall",))
    if cls_name == "ClownCar":
        return T("XB_BOSS_CLOWNCAR", M("sprClownCar"), xs=-3.0, ys=3.0,
                 flags=K | X.XEF_FORCE_ACTIVE,
                 p=[template_for(build, "BowserBomb"),
                    template_for(build, "WartBanzai"),
                    template_for(build, "WartPoof"),
                    template_for(build, "WilyBall"),
                    template_for(build, "WilyFireball"),
                    template_for(build, "OrbBowser"),
                    template_for(build, "BowserFloor"),
                    _path_keys(build, "pBowserSwoosh"),
                    _path_keys(build, "pBowserDash"),
                    X.PROGRESSION_FLAGS["orb_bowser"]],
                 key=("ClownCar",))
    # ---- road / dragon / gradius ----
    if cls_name == "DragonFire":
        return T("XB_DRAGONFIRE", M("sprDragonFire"), xs=3.0, ys=3.0,
                 flags=K, key=("DragonFire",))
    if cls_name == "DragonDevilism":
        return T("XB_DEVILISM", M("sprDragonDevilism"), xs=10.0, ys=10.0,
                 flags=K, key=("DragonDevilism",))
    if cls_name == "blockTrapDestructibleT":
        return T("XB_DESTRUCTIBLE", M("sprGuyFallingBrick"),
                 flags=X.XEF_SOLID | X.XEF_SHOOTABLE, key=("BTDtmpl",))
    if cls_name == "VicBullet":
        return T("XB_VICBULLET", M("sprVicBullet"), xs=2.0, ys=2.0,
                 key=("VicBullet",))
    if cls_name == "GradiusFruit":
        return T("XB_GRADFRUIT", M("sprCherry"), key=("GradiusFruit",))
    if cls_name == "GradiusDroneBullet":
        return T("XB_GRADDRONEBULLET", M("sprGradiusBullets"),
                 key=("GradiusDroneBullet",))
    if cls_name == "vicPlatform":
        return T("XB_EGGPLAT", M("sprDynamicPlatform01"), xs=2.5,
                 flags=X.XEF_PLATFORM, key=("vicPlatform",))
    # ---- the Guy ----
    if cls_name == "GuyFirstBullet":
        return T("XB_GUYPROJ", M("sprBullet"), xs=15.0, ys=15.0, flags=K,
                 p=[0, 0, 0, 0, 0, 1], key=("GuyFirstBullet",))
    if cls_name == "GuySpreadBullet":
        return T("XB_GUYPROJ", M("sprBullet"), xs=44.0, ys=44.0, flags=K,
                 key=("GuySpreadBullet",))
    if cls_name == "GuyShot":
        return T("XB_GUYPROJ", M("sprGuyShot"), flags=K, key=("GuyShot",))
    if cls_name == "Grenade":
        return T("XB_GRENADE", M("sprGrenade"),
                 p=[template_for(build, "WilyFirePillar")],
                 key=("Grenade",))
    if cls_name == "GuyBouncingBullet":
        return T("XB_GUYBOUNCE", M("sprBullet"), xs=15.0, ys=15.0,
                 flags=K, key=("GuyBouncingBullet",))
    if cls_name == "TheGun":
        return T("XB_THEGUN", M("sprTheGun"), key=("TheGun",))
    if cls_name == "GuyTooth":
        return T("XB_GUYTOOTH", M("sprGuyTooth"), flags=K,
                 key=("GuyTooth",))
    if cls_name == "GuyToothShooter":
        return T("XB_TOOTHSHOOTER", 0xffff, key=("GuyToothShooter",))
    if cls_name == "GuyGlassShot":
        return T("XB_GUYGLASSSHOT", M("sprGuyGlassShot"), flags=K,
                 key=("GuyGlassShot",))
    if cls_name == "GuyMouth":
        return T("XB_GUYMOUTH", M("sprGuyMouth"), flags=K,
                 key=("GuyMouth",))
    return None


def _weak_template(build, mask, xs=1.0, ys=1.0, key=None):
    return build.template("XB_WEAKBOX", mask, xs=xs, ys=ys, key=key)


def emit_class(build, ctx, ir_room, inst, obj, x, y, xs, ys, cc, roomvars):
    """Placed boss classes.  True = implemented, None = not ours."""
    from . import exact as X
    M = build.mask
    add = ctx.add
    K = X.XEF_KILLER

    if obj == "MechaBirdo":
        dest = build.room_index["rFactoryOutskirts"]
        p = [_weak_template(build, M("sprBirdoAntenna"), xs=10.0, ys=10.0,
                            key=("wpAntenna",)),
             _weak_template(build, M("spr2x2"), xs=32.0, ys=32.0,
                            key=("wp2x2_32",)),
             _weak_template(build, M("spr2x2"), xs=45.0, ys=44.0,
                            key=("wp2x2_45",)),
             template_for(build, "MechaEgg"),
             template_for(build, "EggPlatform"),
             template_for(build, "EggHitbox"),
             template_for(build, "BirdoLaza"),
             template_for(build, "FlyGuy"),
             dest,
             X.PROGRESSION_FLAGS["orb_birdo"]]
        add("XB_BOSS_BIRDO", x, y, mask=M("sprBirdo"), xs=10.0, ys=10.0,
            flags=X.XEF_FORCE_ACTIVE, p=p, inst=inst)
        return True

    if obj == "KraidgiefFallingSpike":
        add("XB_KGSPIKE", x, y, mask=M("sprKraidgiefSpikeRespawn"),
            xs=xs, ys=ys, flags=K, inst=inst)
        return True
    if obj == "KraidgiefCeiling":
        add("XB_KGCEIL", x, y, mask=M("sprBlockNise"), xs=xs, ys=ys,
            flags=X.XEF_SOLID, inst=inst)
        return True
    if obj == "OrbKraidgief":
        add("XB_ORB", x, y, mask=M("sprUnit"), xs=xs, ys=ys,
            p=[X.PROGRESSION_FLAGS["orb_kraidgief"]], inst=inst)
        return True

    # ---- Tyson (rGuy1) ----
    if obj == "Tyson":
        add("XB_BOSS_TYSON", x, y, mask=M("sprTysonWalk"), xs=6.0, ys=6.0,
            flags=X.XEF_FORCE_ACTIVE | X.XEF_START_INACTIVE,
            p=[_weak_template(build, M("sprTysonFist"),
                              xs=11.0 / 3.0, ys=11.0 / 3.0,
                              key=("wpTysonFist",)),
               template_for(build, "TysonFireball"),
               template_for(build, "OrbTyson"),
               0, 0, 0, 0, 0, 0,
               X.PROGRESSION_FLAGS["orb_tyson"]], inst=inst)
        return True
    if obj == "TysonDoor":
        add("XB_TYSONDOOR", x, y, mask=M("sprTysonDoor"), xs=xs, ys=ys,
            flags=X.XEF_SOLID, inst=inst)
        return True

    # ---- Dracula (rDraculaBoss) ----
    if obj == "DraculaIntro":
        add("XB_BOSS_DRACINTRO", x, y, mask=M("sprDraculaIntro"),
            xs=3.0, ys=3.0, flags=X.XEF_FORCE_ACTIVE,
            p=[template_for(build, "DracGlass"),
               template_for(build, "Dracula"),
               template_for(build, "DracTele")], inst=inst)
        return True
    if obj == "Dracform":
        add("XB_DRACFORM", x, y, mask=M("sprDynamicPlatform01"),
            xs=xs, ys=ys, flags=X.XEF_PLATFORM, inst=inst)
        return True

    # ---- Bowser arena ----
    if obj == "ClownCar":
        tmpl = template_for(build, "ClownCar")
        tag = add("XB_BOSS_CLOWNCAR", x, y, mask=M("sprClownCar"),
                  xs=-3.0, ys=3.0, flags=K | X.XEF_FORCE_ACTIVE,
                  p=list(build.templates[tmpl]["p"]), inst=inst)
        # p8 slot carries the hover path (dash keys live in p8 of the
        # template list order above: p7 swoosh, p8 dash; hover appended)
        ctx.xents[tag]["p"][9] = float(_path_keys(build, "pWilyHover"))
        return True
    if obj == "FallingCeiling":
        add("XB_FCEIL", x, y, mask=M("sprFallingCeiling"), xs=xs, ys=ys,
            flags=K, inst=inst)
        return True
    if obj == "FallingCeilingSpike":
        tag = add("XB_FCSPIKE", x, y, mask=M("sprSpike"), xs=xs, ys=ys,
                  flags=K, inst=inst)
        col = add("XB_KILLER", x, y - 1, mask=build.masks.rect_mask(32, 32),
                  xs=1.0, ys=1.0 / 32.0, flags=K)
        ctx.xents[tag]["link"] = col
        ctx.xents[col]["flags"] |= X.XEF_START_INACTIVE
        return True
    if obj == "FallingCeilingSwitch":
        add("XB_FCSWITCH", x, y, mask=M("sprFallingCeiling"), xs=xs,
            ys=ys, flags=X.XEF_SOLID, inst=inst)
        return True
    if obj == "BowserFloor":
        add("XB_BOWSERFLOOR", x, y, mask=M("sprBowserFloor"), xs=xs,
            ys=ys, flags=X.XEF_SOLID,
            p=[1.0 if x > 400 else 0.0], inst=inst)
        return True
    if obj == "BowserWall":
        add("XB_CONDSOLID", x, y, mask=M("sprBlock"), xs=xs, ys=ys,
            flags=X.XEF_SOLID,
            p=[X.PROGRESSION_FLAGS["orb_bowser"], 0, 0], inst=inst)
        return True

    # ---- Mother Brain (rMetroid) ----
    if obj == "MommyThinker":
        glass = add("XB_MOMMYGLASS", x, y,
                    mask=M("sprMotherHitboxes", per_frame=True),
                    xs=xs, ys=ys, flags=X.XEF_SOLID)
        ctx.xents[glass]["p"][0] = 1.0     # collider uses frame 1
        tag = add("XB_BOSS_MOMMY", x, y,
                  mask=M("sprMotherHitboxes", per_frame=True),
                  xs=xs, ys=ys, flags=X.XEF_FORCE_ACTIVE, inst=inst)
        ctx.xents[tag]["link"] = glass
        return True

    # ---- road bosses ----
    if obj == "RoadMoon":
        add("XB_ROADMOON", x, y, mask=M("sprRoadMoon"), xs=xs, ys=ys,
            flags=X.XEF_FORCE_ACTIVE, inst=inst)
        return True
    if obj == "Dragon":
        dest = build.room_index["rGuyFortress1"]
        add("XB_BOSS_DRAGON", x, y, mask=M("sprDragon", per_frame=True),
            xs=3.0, ys=3.0, flags=K | X.XEF_FORCE_ACTIVE,
            p=[_weak_template(build, build.masks.rect_mask(130, 108),
                              key=("wpDragonFace",)),
               template_for(build, "DragonFire"),
               template_for(build, "DragonDevilism"),
               template_for(build, "blockTrapDestructibleT"),
               0, 0, 0, 0, dest,
               X.PROGRESSION_FLAGS["orb_dragon"]], inst=inst)
        return True
    if obj in ("DragonMarker", "DragonMarker2"):
        kind = (X.XM_DRAGONTURN if obj == "DragonMarker"
                else X.XM_DRAGONDEAD)
        add("XB_MARKER", x, y, mask=M("sprControllerMMF2"), xs=xs, ys=ys,
            p=[kind], inst=inst)
        return True
    if obj == "DragonBlock":
        add("XB_DRAGONBLOCK", x, y, mask=M("sprFactoryYoku"), xs=xs,
            ys=ys, p=[template_for(build, "blockTrapDestructibleT")],
            inst=inst)
        return True
    if obj == "Sinistar":
        add("XB_SINISTAR", x, y, mask=M("sprSinistar"), xs=3.0, ys=3.0,
            flags=X.XEF_FORCE_ACTIVE, inst=inst)
        return True
    if obj == "LuBooHoo":
        # torch gag: absorbs the BowserFireClassic that flies past
        # (Collision_BowserFireClassic -> with(other) instance_destroy;
        # the reveal itself is visual)
        add("XB_MARKER", x, y, mask=M("sprLuBuFace"), xs=xs, ys=ys,
            p=[X.XM_FIRESINK], inst=inst)
        return True
    if obj == "VicViper":
        add("XB_VICVIPER", x, y, mask=M("sprVic"), xs=3.0, ys=3.0,
            flags=X.XEF_FORCE_ACTIVE,
            p=[template_for(build, "VicBullet"),
               template_for(build, "vicPlatform")], inst=inst)
        return True
    if obj == "GradiusMarker":
        add("XB_MARKER", x, y, mask=M("sprBlockNise"), xs=xs, ys=ys,
            p=[X.XM_GRADIUS], inst=inst)
        return True
    if obj == "GradiusBugz":
        add("XB_GRADBUGZ", x, y + 16, mask=M("sprDumbBugz"), xs=-1.0,
            flags=X.XEF_FORCE_ACTIVE, inst=inst)
        return True
    if obj == "GradiusDrones":
        add("XB_GRADDRONE", x + 16, y + 8, mask=M("sprTurret"),
            flags=X.XEF_FORCE_ACTIVE,
            p=[template_for(build, "GradiusDroneBullet")], inst=inst)
        return True
    if obj == "GradiusBoss":
        add("XB_GRADBOSS", x + 16, y, mask=M("sprTurret"),
            flags=X.XEF_FORCE_ACTIVE,
            p=[template_for(build, "GradiusFruit")], inst=inst)
        return True

    # ---- Arkanoid (rGuyFortress2) ----
    if obj == "ArkaBall":
        add("XB_ARKABALL", x, y, mask=M("sprCherry"), xs=xs, ys=ys,
            flags=K | X.XEF_FORCE_ACTIVE, inst=inst)
        return True
    if obj == "ArkaPlatform":
        add("XB_ARKAPADDLE", x, y, mask=M("sprBreakout"), xs=xs, ys=ys,
            flags=X.XEF_FORCE_ACTIVE, inst=inst)
        return True
    if obj in ("ArkaBrick", "ArkaBrickShort"):
        short = obj == "ArkaBrickShort"
        spr = "sprArkaBrickSmall" if short else "sprArkaBlock"
        tag = add("XB_ARKABRICK", x, y, mask=M(spr), xs=xs, ys=ys,
                  flags=X.XEF_SOLID, inst=inst)
        ctx.xents[tag]["p"][0] = x + (16.0 if short else 32.0)
        ctx.xents[tag]["p"][1] = y + 16.0
        ctx.xents[tag]["p"][2] = 1.0 if short else 0.0
        return True

    # ---- the Guy (rGuyBoss) ----
    if obj == "GuyFirst":
        add("XB_BOSS_GUYFIRST", x, y, mask=M("sprGuyStand"), xs=-1.0,
            flags=K | X.XEF_FORCE_ACTIVE,
            p=[template_for(build, "GuyFirstBullet"),
               template_for(build, "GuySpreadBullet"),
               template_for(build, "Grenade"),
               template_for(build, "WilyFirePillar"),
               template_for(build, "GuyBouncingBullet"),
               template_for(build, "TheGun"),
               _path_keys(build, "pGuyJump")], inst=inst)
        return True
    if obj == "GuyHead":
        dest = build.room_index["rEnding"]
        add("XB_BOSS_GUYHEAD", x, y, mask=M("sprGuyHead"), xs=40.0,
            ys=40.0, flags=X.XEF_FORCE_ACTIVE,
            p=[template_for(build, "GuyShot"),
               template_for(build, "GuyTooth"),
               template_for(build, "GuyToothShooter"),
               template_for(build, "GuyGlassShot"),
               template_for(build, "WilyFirePillar"),
               template_for(build, "GuyMouth"),
               0, 0,
               X.PROGRESSION_FLAGS["orb_guy"], dest], inst=inst)
        return True
    if obj == "Geye":
        add("XB_GEYE", x, y, mask=M("sprGeyeNuts"),
            flags=X.XEF_FORCE_ACTIVE, inst=inst)
        return True
    if obj == "Guybrow":
        add("XB_GUYBROW", x, y, mask=M("sprGuybrow"), xs=xs * 10.0,
            ys=10.0, inst=inst)
        return True

    return None


def enter_ops_for(build, rname):
    """Flag-gated arena state, compiled to room-enter op programs."""
    from . import exact as X
    if rname == "rMechaBirdoBoss":
        dest = build.room_index["rFactoryOutskirts"]
        ops = [("XOP_IF_FLAG", X.TGT_NONE,
                X.PROGRESSION_FLAGS["orb_birdo"], 1, 0),
               ("XOP_GOTO_ROOM", X.TGT_NONE, dest, 32, 624)]
        return build.asm.emit(ops)
    if rname == "rKraidgiefBoss":
        body = [("XOP_CAM_MODE", X.TGT_NONE, 0, 0, 0),
                ("XOP_DESTROY", X.TGT_CLS0 - X.C["XB_KGCEIL"], 0, 0, 0),
                ("XOP_DESTROY", X.TGT_CLS0 - X.C["XB_DESTRUCTIBLE"],
                 0, 0, 0),
                ("XOP_DESTROY", X.TGT_CLS0 - X.C["XB_KGSPIKE"], 0, 0, 0),
                ("XOP_DESTROY", X.TGT_CLS0 - X.C["XB_BOLT"], 0, 0, 0),
                ("XOP_DESTROY", X.TGT_CLS0 - X.C["XB_TRIGGER"], 0, 0, 0)]
        ops = [("XOP_IF_FLAG", X.TGT_NONE,
                X.PROGRESSION_FLAGS["orb_kraidgief"], len(body), 0)] + body
        return build.asm.emit(ops)
    if rname == "rGuy1":
        # Tyson's doors leave with him once orb_tyson is set (the source
        # destroys them at victory; a reload must not restore them)
        body = [("XOP_DESTROY", X.TGT_CLS0 - X.C["XB_TYSONDOOR"], 0, 0, 0)]
        ops = [("XOP_IF_FLAG", X.TGT_NONE,
                X.PROGRESSION_FLAGS["orb_tyson"], len(body), 0)] + body
        return build.asm.emit(ops)
    if rname == "rBowserBoss":
        # ClownCar Create: savedata("orb_bowser") -> instance_destroy()
        # (BowserWall opens itself via XB_CONDSOLID)
        body = [("XOP_DESTROY", X.TGT_CLS0 - X.C["XB_BOSS_CLOWNCAR"],
                 0, 0, 0)]
        ops = [("XOP_IF_FLAG", X.TGT_NONE,
                X.PROGRESSION_FLAGS["orb_bowser"], len(body), 0)] + body
        return build.asm.emit(ops)
    return (0, 0)
