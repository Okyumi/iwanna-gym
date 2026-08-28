"""Boss-arena conversion for iwbtgr_1_5_3 (milestone: boss framework).

Emits the exact-layer content of the two ported boss arenas —
rMechaBirdoBoss (MechaBirdo) and rKraidgiefBoss (Kraidgief) — on top of
the machinery in exact.py: the same coverage gates apply (an instance
that matches nothing here or in exact.py fails the build), boss bodies
and their runtime spawns become templates/entities whose parameters come
straight from the source GML, and the flag-gated arena states (fight not
yet won / already won) compile to room-enter op programs.

The C side lives in c_src/boss/ (framework + one file per boss).
Everything here only *places* data; behavior constants are transliterated
in C with the source lines cited in docs/boss_architecture.md.
"""
from __future__ import annotations

#: rooms converted by this module (in addition to exact.GAMEPLAY_ROOMS)
BOSS_ROOMS = ["rMechaBirdoBoss", "rKraidgiefBoss"]

#: Kraidgief body sprites, indexed by the C-side KGS_* enum; the mask ids
#: are baked into the keys pool at body-template build time
KG_SPRITES = [
    "sprKraidgiefWalk", "sprKraidgiefChop", "sprKraidgiefPunch",
    "sprKraidgiefLariet", "sprKraidgiefChargeUp", "sprKraidgiefHeadbutt",
    "sprKraidgiefAngryStand", "sprKraidgiefFire", "sprKraidgiefGrab",
    "sprKraidgiefSPD", "sprKraidgiefShit", "sprKraidgiefDying",
]


def template_for(build, cls_name):
    """Boss-family runtime-spawn templates (None: not a boss class)."""
    from . import exact as X
    M = build.mask
    T = build.template
    if cls_name == "MechaEgg":
        return T("XB_MECHAEGG", M("sprEgg"), key=("MechaEgg",))
    if cls_name == "EggPlatform":
        return T("XB_EGGPLAT", M("sprDynamicPlatform01"), xs=137.0 / 32.0,
                 flags=X.XEF_PLATFORM, key=("EggPlatform",))
    if cls_name == "EggHitbox":
        return T("XB_EGGHITBOX", M("sprEggHitbox"), flags=X.XEF_KILLER,
                 key=("EggHitbox",))
    if cls_name == "BirdoLaza":
        return T("XB_LAZA", M("sprLaza"), flags=X.XEF_KILLER,
                 key=("BirdoLaza",))
    if cls_name == "FlyGuy":
        return T("XB_FLYGUY", M("sprFlyGuy"), xs=-2.0, ys=2.0,
                 flags=X.XEF_SHOOTABLE, key=("FlyGuy",))
    if cls_name == "KGHadouken":
        return T("XB_KGPROJ", M("sprKGHadouken"), flags=X.XEF_KILLER,
                 key=("KGHadouken",))
    if cls_name == "KGFireDown":
        return T("XB_KGFIRE", M("sprKGFireDown"), xs=4.75, ys=4.75,
                 flags=X.XEF_KILLER, key=("KGFireDown",))
    if cls_name == "KGFireSide":
        return T("XB_KGFIRE", M("sprKGFireSide"), xs=5.5, ys=5.5,
                 flags=X.XEF_KILLER, key=("KGFireSide",))
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
                 xs=5.5, ys=5.5,
                 flags=X.XEF_KILLER | X.XEF_FORCE_ACTIVE,
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
    return None


def _weak_template(build, mask, xs=1.0, ys=1.0, key=None):
    return build.template("XB_WEAKBOX", mask, xs=xs, ys=ys, key=key)


def emit_class(build, ctx, ir_room, inst, obj, x, y, xs, ys, cc, roomvars):
    """Placed boss-arena classes.  True = implemented (tallied as boss),
    None = not ours."""
    from . import exact as X
    M = build.mask
    add = ctx.add

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
            xs=xs, ys=ys, flags=X.XEF_KILLER, inst=inst)
        return True

    if obj == "KraidgiefCeiling":
        add("XB_KGCEIL", x, y, mask=M("sprBlockNise"), xs=xs, ys=ys,
            flags=X.XEF_SOLID, inst=inst)
        return True

    if obj == "OrbKraidgief":
        add("XB_ORB", x, y, mask=M("sprUnit"), xs=xs, ys=ys,
            p=[X.PROGRESSION_FLAGS["orb_kraidgief"]], inst=inst)
        return True

    return None


def enter_ops_for(build, rname):
    """Flag-gated arena state, compiled to room-enter op programs.

    - rMechaBirdoBoss: MechaBirdo Create with savedata("orb_birdo") set
      warps the player straight on to rFactoryOutskirts (32,624); the
      boss record itself stays dead (loader check on p9).
    - rKraidgiefBoss: the arena trigger's create code with
      savedata("orb_kraidgief") set unlocks the camera and clears the
      ceiling, destructible blocks, falling spikes, floor spikes and the
      trigger itself, leaving a plain corridor to the exit warp.
    """
    from . import exact as X
    if rname == "rMechaBirdoBoss":
        dest = build.room_index["rFactoryOutskirts"]
        ops = [("XOP_IF_FLAG", X.TGT_NONE,          # run only when won
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
        ops = [("XOP_IF_FLAG", X.TGT_NONE,          # run only when won
                X.PROGRESSION_FLAGS["orb_kraidgief"], len(body), 0)] + body
        return build.asm.emit(ops)
    return (0, 0)
