"""IWBTGR 1.5.3 exact-behavior converter (milestone: non-boss rooms).

Translates every gameplay-relevant non-boss object class of the source
into compiled native behaviors (pack v3 "exact" section): sprite collision
masks decoded from the source PNG alpha, per-class entity records with
source constants, compiled trigger programs (every creation-code string
must match a known pattern or the build FAILS), offline-sampled GM paths,
and the offline-simulated tetris timeline.

Reference: docs/iwbtgr_nonboss_mechanics.md (per-class source semantics).
Nothing here invents mechanics: constants come from the parsed GML and
sprite metadata; unknown content raises ConversionError (coverage gate).
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from typing import Any

from .converter import (ConversionError, PROGRESSION_FLAGS, META_ROOMS,
                        _parse_assigns, TILE)

# ---------------------------------------------------------------------------
# Mirrors of the C enums (c_src/exact.h) — order is load-bearing.
# ---------------------------------------------------------------------------
XCLS = """XB_MARKER XB_KILLER XB_ANIM_KILLER XB_SHAKE_FALL XB_BOLT
XB_SPIKE_EXTEND XB_REVEALING XB_SPIKETRAP XB_QUICKLASER XB_QLTIMER
XB_KILLPLANE XB_HIGGER XB_ERRORTRAP XB_PAINTING XB_WHEEL XB_FLYSPIKE
XB_GUTSMAN XB_COUCH XB_HAMMER XB_SPIKESHOOT XB_MEDUSA XB_MEDUSAMAKER
XB_BIRD XB_GHOUL XB_GHOULGEN XB_HOVERGUNNER XB_HOVERSHOT XB_SNIPER
XB_TOURTURRET XB_SKWEE XB_CRAWLER XB_DUMBBUGZ XB_METROID XB_METROIDTRAP
XB_SPAGDISP XB_SPAG XB_ROLLROCK XB_WATCHFOR XB_PLAYSTATION XB_KAMEK
XB_EGGPLANT XB_BOUNCYFRUIT XB_WITCH XB_WITCHSHADOW XB_LONK XB_CHEEP
XB_CHEEPCTL XB_BULLETBILL XB_MOVPLAT XB_FALLPLAT XB_METROIDPLAT XB_ASCENT
XB_ASCENTMOD XB_KUMO XB_GUYPLAT XB_PILLAR XB_HILL XB_CART XB_CARTPICKUP
XB_FACTORYCTL XB_FACTORYBLOCK XB_REALYOKUCTL XB_REALYOKU XB_TETRIS
XB_TETBLOCK XB_KILLPILL XB_BUTTON XB_SHOOTBARRIER XB_NATSCAT XB_BOOM
XB_CHOZO XB_TRIGGER XB_LOCKCONTROLS XB_FRUIT XB_CATTHING XB_FIRECHALICE
XB_RYU XB_RYUWIND XB_MOONSMALL XB_MOONBIG XB_ORB XB_SECRET XB_ENTRANCETELE
XB_CONDSOLID XB_TOURIANBARRIER XB_DESTRUCTIBLE XB_WALLSTRIP XB_WATER
XB_SNIFITCANNON XB_SNIFITBULLET XB_ZELDAOLDMAN XB_PATHKILLER XB_FRSPIKE
XB_FRBARRIER XB_SPIKEMAN XB_SPINNER
XB_WEAKBOX XB_BOSS_TEST XB_BOSS_BIRDO XB_MECHAEGG XB_EGGPLAT XB_EGGHITBOX
XB_LAZA XB_FLYGUY XB_BOSS_KRAIDGIEF XB_KGPROJ XB_KGFIRE XB_BLANKA
XB_KGDEBRISSPAWN XB_KGDEBRIS XB_KGSPIKE XB_KGCEIL
XB_BOSS_TYSON XB_TYSONFIREBALL XB_TYSONDOOR
XB_BOSS_DRACINTRO XB_BOSS_DRACULA XB_BOSS_DEADCULA XB_DRACTELE
XB_DRACGLASS XB_DRACPROJ XB_DRACFIREBALL XB_DRACSPIRAL XB_DRACPLASM
XB_WILYPILLAR
XB_BOSS_CLOWNCAR XB_BOWSERBOMB XB_BOWSEREXPL XB_BOWSERFIRE XB_WARTBANZAI
XB_WARTPOOF XB_WILYBALL XB_WILYFIREBALL XB_FCEIL XB_FCSPIKE XB_FCSWITCH
XB_BOWSERFLOOR
XB_BOSS_MOMMY XB_MOMMYGLASS
XB_BOSS_DRAGON XB_DRAGONFIRE XB_DEVILISM XB_DRAGONBLOCK XB_ROADMOON
XB_SINISTAR
XB_VICVIPER XB_VICBULLET XB_GRADBOSS XB_GRADBUGZ XB_GRADDRONE
XB_GRADDRONEBULLET XB_GRADFRUIT
XB_ARKABALL XB_ARKAPADDLE XB_ARKABRICK
XB_BOSS_GUYFIRST XB_GUYPROJ XB_GRENADE XB_GUYBOUNCE
XB_BOSS_GUYHEAD XB_GEYE XB_GUYMOUTH XB_GUYTOOTH XB_TOOTHSHOOTER
XB_GUYGLASSSHOT XB_GUYBROW XB_THEGUN XB_DRACFORM""".split()
C = {name: i for i, name in enumerate(XCLS)}

XOPS = """XOP_END XOP_SET_ACTIVE XOP_ARM XOP_SET_VX XOP_SET_VY XOP_SET_FSPD
XOP_SET_STATE XOP_ADD_STATE XOP_EVENT XOP_SPAWN XOP_DESTROY XOP_KILL_PLAYER
XOP_FREEZE_PLAYER XOP_SET_FIRE XOP_SET_FLAG XOP_GOTO_ROOM XOP_IF_STATE_EQ
XOP_IF_STATE_NE XOP_IF_ALIVE XOP_IF_DEAD XOP_IF_FLAG XOP_IF_NOT_FLAG
XOP_IF_PLAYER_FIRE XOP_IF_Y_LT XOP_IF_VY_LE XOP_IF_X_LT XOP_IF_OVERLAP
XOP_IF_WITCH_WAIT XOP_SET_FRAME XOP_LAST_FRAME XOP_SET_TIMER XOP_SET_P
XOP_SPAWNBOOST XOP_IF_P_EQ XOP_CAM_MODE""".split()
OP = {name: i for i, name in enumerate(XOPS)}

# marker kinds (XB_MARKER p0) — mirrors the C enum
(XM_GENERIC, XM_BOUNCE_UP, XM_BOUNCE_DOWN, XM_BOUNCE_LEFT, XM_BOUNCE_RIGHT,
 XM_BLOCKNISE, XM_KUMOSTOP, XM_DUMP, XM_BULLETTRIGGER, XM_CARTSTOP,
 XM_MEDUSAMOD, XM_SOFTLOCK, XM_FRSW, XM_WALLJUMP_GONE,
 XM_DRAGONTURN, XM_DRAGONDEAD, XM_GRADIUS, XM_FIRESINK) = range(18)

XW_PLAIN, XW_YELLOW, XW_WEIRD = 0, 1, 2
XCAM_NONE, XCAM_HARD, XCAM_CART, XCAM_TOWER, XCAM_HARD_METROID, \
    XCAM_KRAID = 0, 1, 2, 3, 4, 5

XEF_KILLER = 1
XEF_SOLID = 2
XEF_PLATFORM = 4
XEF_SHOOTABLE = 8
XEF_FORCE_ACTIVE = 16
XEF_START_INACTIVE = 32
XEF_NOPUSH = 64
XEF_STOPPER = 128
XEF_NOBOUNCE = 256
XEF_MIRROR8 = 512

TGT_SELF, TGT_PLAYER, TGT_NONE, TGT_CLS0 = -1, -2, -3, -1000

#: the 14 non-boss gameplay rooms of this milestone
GAMEPLAY_ROOMS = ["rCastlevania", "rFactoryOutskirts", "rGraveyard", "rGuy1",
                  "rGuyEntrance", "rGuyFortress1", "rGuyFortress2",
                  "rGuyLabyrinth", "rGuyRoad", "rGuyTower", "rKraidgiefLair",
                  "rMegaman", "rMetroid", "rZelda"]

ROOM_CAMERA = {"cameraHard": XCAM_HARD, "cameraCart": XCAM_CART,
               "cameraTower": XCAM_TOWER, "cameraKraid": XCAM_KRAID}

MMFS = 1 / 8.0        # mmf_speed(n)  = n/8   (scripts/mmf_speed.gml)
MMFA = 1 / 100.0      # mmf_animspeed = n/100


# ---------------------------------------------------------------------------
# Sprite masks
# ---------------------------------------------------------------------------

class MaskTable:
    """Collision masks decoded from the source sprite PNGs (per frame when
    the sprite uses per-frame colliders or an animated mask matters)."""

    def __init__(self, source_root: str, proj):
        self.root = source_root
        self.proj = proj
        self.masks: list[dict[str, Any]] = []
        self._by_key: dict[tuple, int] = {}

    def _sprite_dir(self, name):
        return os.path.join(self.root, "sprites", name)

    def get(self, sprite: str, per_frame: bool | None = None) -> int:
        spr = self.proj.sprites.get(sprite)
        if spr is None:
            raise ConversionError(f"unknown sprite {sprite!r}")
        p = spr.props
        want_pf = bool(p.get("per_frame_colliders", 0)) \
            if per_frame is None else per_frame
        key = (sprite, want_pf)
        if key in self._by_key:
            return self._by_key[key]
        shape = int(p.get("collision_shape", 0))
        tol = int(p.get("alpha_tolerance", 0))
        rec = {
            "sprite": sprite,
            "ox": int(p.get("origin_x", 0)), "oy": int(p.get("origin_y", 0)),
            "bl": int(p.get("bbox_left", 0)), "bt": int(p.get("bbox_top", 0)),
            "br": int(p.get("bbox_right", 0)),
            "bb": int(p.get("bbox_bottom", 0)),
            "shape": 0 if shape == 1 else 1,   # C: 0 rect, 1 precise
            "frames": [],
            "w": 0, "h": 0,
        }
        d = self._sprite_dir(sprite)
        pngs = sorted((f for f in os.listdir(d) if f.endswith(".png")),
                      key=lambda f: int(f[:-4]))
        if not pngs:
            raise ConversionError(f"sprite {sprite} has no frames")
        from PIL import Image
        frames = []
        for fn in pngs:
            im = Image.open(os.path.join(d, fn)).convert("RGBA")
            frames.append(im)
        rec["w"], rec["h"] = frames[0].size
        if shape == 1 and want_pf:
            # GM: rectangle shape + per-frame colliders = each frame's
            # bounding RECT of its alpha (empty frame -> empty collider)
            rec["shape"] = 1
            per = []
            for im in frames:
                w, h = rec["w"], rec["h"]
                alpha = list(im.getdata(3))
                xs_ = [i % w for i, a in enumerate(alpha) if a > tol]
                ys_ = [i // w for i, a in enumerate(alpha) if a > tol]
                rows = [0] * h
                if xs_:
                    x0, x1 = min(xs_), max(xs_)
                    fill = ((1 << (x1 + 1)) - 1) ^ ((1 << x0) - 1)
                    for y in range(min(ys_), max(ys_) + 1):
                        rows[y] = fill
                per.append(rows)
            rec["frames"] = per
            idx = len(self.masks)
            self.masks.append(rec)
            self._by_key[key] = idx
            return idx
        if rec["shape"] == 1:              # precise: decode alpha bitmaps
            use = frames if want_pf else frames[:]
            per = []
            for im in (use if want_pf else [None]):
                w, h = rec["w"], rec["h"]
                rows = [0] * h
                if want_pf:
                    alpha = im.getdata(3)
                    for i, a in enumerate(alpha):
                        if a > tol:
                            rows[i // w] |= 1 << (i % w)
                else:
                    for fim in frames:     # union of all frames (GM8 rule)
                        alpha = fim.getdata(3)
                        for i, a in enumerate(alpha):
                            if a > tol:
                                rows[i // w] |= 1 << (i % w)
                per.append(rows)
            rec["frames"] = per
        idx = len(self.masks)
        self.masks.append(rec)
        self._by_key[key] = idx
        return idx

    def rect_mask(self, w: int, h: int, ox: int = 0, oy: int = 0) -> int:
        """Synthetic rectangle mask (for runtime colliders with no sprite)."""
        key = ("__rect__", w, h, ox, oy)
        if key in self._by_key:
            return self._by_key[key]
        rec = {"sprite": f"rect{w}x{h}", "ox": ox, "oy": oy,
               "bl": 0, "bt": 0, "br": w - 1, "bb": h - 1,
               "shape": 0, "frames": [], "w": w, "h": h}
        idx = len(self.masks)
        self.masks.append(rec)
        self._by_key[key] = idx
        return idx

    def spans(self, sprite: str, frame: int = 0):
        """Solid row spans of a precise mask (for static rasterization)."""
        idx = self.get(sprite, per_frame=True)
        rec = self.masks[idx]
        if rec["shape"] == 0:
            yield from ((y, rec["bl"], rec["br"])
                        for y in range(rec["bt"], rec["bb"] + 1))
            return
        rows = rec["frames"][frame]
        for y in range(rec["bt"], rec["bb"] + 1):
            bits = rows[y]
            x = rec["bl"]
            while x <= rec["br"]:
                if (bits >> x) & 1:
                    x0 = x
                    while x <= rec["br"] and (bits >> x) & 1:
                        x += 1
                    yield (y, x0, x - 1)
                else:
                    x += 1


# ---------------------------------------------------------------------------
# GM path sampling (offline). Straight + smooth (precision-4 quadratic).
# ---------------------------------------------------------------------------

def _path_polyline(points, smooth: bool, closed: bool, precision: int = 4):
    """GM8 path internal polyline. Smooth paths: quadratic corner-cutting
    through segment midpoints with 2^precision subdivisions (repeated
    anchor points pin the curve, as the source paths rely on)."""
    pts = [(float(x), float(y), float(sp)) for x, y, sp in points]
    if not smooth:
        return pts if not closed else pts + [pts[0]]
    if closed:
        ring = pts
        n = len(ring)
        out = []
        subs = 1 << precision
        for i in range(n):
            p0 = ring[i]
            p1 = ring[(i + 1) % n]
            p2 = ring[(i + 2) % n]
            m01 = [(p0[k] + p1[k]) / 2 for k in range(3)]
            m12 = [(p1[k] + p2[k]) / 2 for k in range(3)]
            for s in range(subs):
                t = s / subs
                a = (1 - t) ** 2
                b = 2 * t * (1 - t)
                c = t * t
                out.append(tuple(a * m01[k] + b * p1[k] + c * m12[k]
                                 for k in range(3)))
        out.append(out[0])
        return out
    n = len(pts)
    if n < 3:
        return pts
    out = [pts[0]]
    subs = 1 << precision
    for i in range(n - 2):
        p0, p1, p2 = pts[i], pts[i + 1], pts[i + 2]
        m01 = [(p0[k] + p1[k]) / 2 for k in range(3)]
        m12 = [(p1[k] + p2[k]) / 2 for k in range(3)]
        start = 0 if i > 0 else 0
        for s in range(start, subs + (1 if i == n - 3 else 0)):
            t = s / subs
            a = (1 - t) ** 2
            b = 2 * t * (1 - t)
            c = t * t
            out.append(tuple(a * m01[k] + b * p1[k] + c * m12[k]
                             for k in range(3)))
    out.append(pts[-1])
    return out


def sample_path(points, smooth, closed, speed, max_frames=20000,
                loops=1):
    """Per-frame positions advancing `speed * sp/100` px along the
    polyline each frame (GM8 path runner)."""
    poly = _path_polyline(points, smooth, closed)
    segs = []
    total = 0.0
    for i in range(len(poly) - 1):
        x0, y0, s0 = poly[i]
        x1, y1, s1 = poly[i + 1]
        d = math.hypot(x1 - x0, y1 - y0)
        segs.append((x0, y0, x1, y1, s0, s1, d, total))
        total += d
    if total <= 0:
        return [(poly[0][0], poly[0][1])]
    out = []
    dist = 0.0
    limit = total * loops
    si = 0
    frames = 0
    while dist < limit and frames < max_frames:
        dmod = dist % total
        while si < len(segs) - 1 and \
                dmod >= segs[si][7] + segs[si][6]:
            si += 1
        if dmod < segs[si][7]:
            si = 0
            while si < len(segs) - 1 and \
                    dmod >= segs[si][7] + segs[si][6]:
                si += 1
        x0, y0, x1, y1, s0, s1, d, off = segs[si]
        t = 0.0 if d == 0 else (dmod - off) / d
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        sp = s0 + (s1 - s0) * t
        out.append((x, y))
        dist += max(1e-6, speed * sp / 100.0)
        frames += 1
    return out


# ---------------------------------------------------------------------------
# Trigger-code compilation. Every i/o/t/c creation-code string in the 14
# rooms must be matched by a rule here — otherwise the build FAILS with the
# raw string (coverage gate: nothing is dropped silently).
# ---------------------------------------------------------------------------

_NUM_EXPR = re.compile(r"^[-+0-9*/(). ]+$")


def _fold(expr: str) -> float:
    """Constant-fold arithmetic in spawn coordinates like 1700-800-14."""
    expr = expr.strip()
    if not _NUM_EXPR.match(expr):
        raise ConversionError(f"non-constant expression {expr!r}")
    return float(eval(expr, {"__builtins__": {}}))  # noqa: S307 (folded consts)


def _mmf(expr: str) -> float:
    expr = expr.strip()
    m = re.fullmatch(r"-?mmf_speed\(\s*(-?\d+(?:\.\d+)?)\s*\)", expr)
    if m:
        v = float(m.group(1)) / 8.0
        return -v if expr.startswith("-") else v
    m = re.fullmatch(r"mmf_animspeed\(\s*(-?\d+)\s*\)", expr)
    if m:
        return float(m.group(1)) / 100.0
    return _fold(expr)


class OpAsm:
    """Flat op pool assembler."""

    def __init__(self):
        self.ops: list[list[float]] = []

    def emit(self, ops: list[tuple]) -> tuple[int, int]:
        """ops: (opname, tgt, a, b, c) tuples -> (first, count)."""
        first = len(self.ops)
        for name, tgt, a, b, c in ops:
            self.ops.append([OP[name], int(tgt), float(a), float(b), float(c)])
        return first, len(ops)


class TriggerCompiler:
    """Compiles the i / o / t / c strings of `trigger` instances (and the
    warp `code=` strings) into op programs against the room's entity map."""

    def __init__(self, ctx):
        self.ctx = ctx        # RoomCtx

    # -- target resolution ---------------------------------------------------
    def resolve_target(self, expr: str, inst):
        expr = expr.strip()
        ctx = self.ctx
        if expr == "id":
            return TGT_SELF
        if expr == "player":
            return TGT_PLAYER
        if expr == "0":
            return TGT_NONE
        m = re.fullmatch(r"instance_place\(x,\s*y,\s*(\w+)\)", expr)
        if m:
            # compile-time geometric resolution: the instance of that class
            # overlapping this trigger's rect
            cands = ctx.overlapping_of_class(inst, m.group(1))
            if len(cands) != 1:
                raise ConversionError(
                    f"instance_place target ambiguous ({len(cands)} hits) "
                    f"for trigger {inst.id_hex} in {ctx.rname}")
            return cands[0]
        if re.fullmatch(r"r\w+_[0-9A-F]{8}", expr):
            return ctx.ent_by_hex(expr.split("_")[-1])
        if expr in self.ctx.proj.objects:
            cls = self.ctx.class_of_object(expr)
            return TGT_CLS0 - cls
        raise ConversionError(f"unresolvable trigger target {expr!r}")

    # -- statement compilation ----------------------------------------------
    def compile_code(self, code: str, inst, default_tgt):
        """Compile one o/t/c string to an op list. Raises on anything not
        recognized (the coverage gate)."""
        code = code.strip()
        ops: list[tuple] = []
        # normalize: strip sounds/music (audio is not gameplay)
        code = re.sub(r"play_sound(?:_pitch)?\([^)]*\)", "", code)
        code = re.sub(r"play_music\([^)]*\)", "", code)
        stmts = self._split(code)
        for st in stmts:
            ops.extend(self._stmt(st, inst, default_tgt))
        return ops

    def _split(self, code):
        # top-level split on newline/;, keeping {...} groups intact
        out, depth, cur = [], 0, []
        for ch in code:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if ch in "\n;" and depth == 0:
                s = "".join(cur).strip()
                if s:
                    out.append(s)
                cur = []
            else:
                cur.append(ch)
        s = "".join(cur).strip()
        if s:
            out.append(s)
        return out

    def _stmt(self, st, inst, tgt):
        ctx = self.ctx
        st = st.strip()
        if not st or st.startswith("//"):
            return []

        # -- with (X) BODY --------------------------------------------------
        m = re.fullmatch(r"with\s*\(([^)]+)\)\s*(.*)", st, re.S)
        if m:
            sub_tgt_expr, body = m.group(1).strip(), m.group(2).strip()
            if body.startswith("{") and body.endswith("}"):
                body = body[1:-1]
            # special geometric form:
            #   with (Cls) if place_meeting(x+DX,y,other...) { ... }
            pm = re.match(r"if\s*\(?\s*place_meeting\(x([+-]\d+)?,\s*y,"
                          r"\s*other(?:\.id)?\)\s*\)?\s*(.*)", body, re.S)
            if pm and sub_tgt_expr in ctx.proj.objects:
                dx = float(pm.group(1) or 0)
                inner = pm.group(2).strip()
                if inner.startswith("{") and inner.endswith("}"):
                    inner = inner[1:-1]
                targets = ctx.overlapping_of_class(inst, sub_tgt_expr, dx=dx,
                                                   all_hits=True)
                ops = []
                for t2 in targets:
                    for s2 in self._split(inner):
                        ops.extend(self._stmt(s2, inst, t2))
                return ops
            if sub_tgt_expr == "player" and "instance_destroy" in body:
                return []  # paired with room_goto (fresh spawn at target)
            sub_tgt = self.resolve_target(sub_tgt_expr, inst)
            ops = []
            for s2 in self._split(body):
                ops.extend(self._stmt(s2, inst, sub_tgt))
            return ops

        # -- collision_rectangle guard: instance filtering already happened
        # at conversion time (e.g. rBowserBoss spikeDown-in-rect became
        # XB_FCEIL ents), so the guard is stripped and the body compiled.
        m = re.fullmatch(r"if\s*\(collision_rectangle\([^)]*\)\)\s*(.*)",
                         st, re.S)
        if m:
            return self._stmt(m.group(1).strip(), inst, tgt)

        # -- guarded composites (the exact source shapes) -------------------
        m = re.fullmatch(
            r"if\s*\(\s*!active\s*\)\s*\{(.*)\}", st, re.S)
        if m:  # FirstRoomSpike c-pattern: if (!active) {active=true ...}
            inner = self._split(m.group(1))
            body_ops = []
            for s2 in inner:
                body_ops.extend(self._stmt(s2, inst, tgt))
            return [("XOP_IF_STATE_EQ", tgt, 0, len(body_ops), 0)] + body_ops

        m = re.fullmatch(r"if\s*\(\s*!Witch\.valid\s*\)\s*(.*)", st, re.S)
        if m:
            body = self._stmt(m.group(1), inst, tgt)
            return [("XOP_IF_WITCH_WAIT", tgt, 0, len(body), 0)] + body

        m = re.fullmatch(r"if\s*\(\s*(?:other\.)?yes\s*\)\s*(.*)", st, re.S)
        if m:
            body = self._stmt(m.group(1), inst, tgt)
            # `yes` lives on the trigger itself (p[7])
            return [("XOP_IF_P_EQ", TGT_SELF, 1, len(body), 7)] + body

        m = re.fullmatch(
            r"if\s*\(\s*savedata\(['\"](\w+)['\"]\)\s*\)\s*\{(.*)\}",
            st, re.S)
        if m:
            flag = PROGRESSION_FLAGS[m.group(1)]
            body = []
            for s2 in self._split(m.group(2)):
                body.extend(self._stmt(s2, inst, tgt))
            return [("XOP_IF_FLAG", TGT_NONE, flag, len(body), 0)] + body

        m = re.fullmatch(r"if\s*\(\s*instance_exists\((\w+)\)\s*\)\s*(.*)",
                         st, re.S)
        if m:
            cls_name = m.group(1)
            if ctx.is_excluded_class(cls_name):
                return []                      # boss-only cosmetic guard
            cls = ctx.class_of_object(cls_name)
            body = self._stmt(m.group(2), inst, tgt)
            return [("XOP_IF_ALIVE", TGT_CLS0 - cls, 0, len(body), 0)] + body

        m = re.fullmatch(r"if\s*\(\s*y\s*<\s*(\d+)\s*&&\s*vspeed\s*<=\s*0\s*"
                         r"\)\s*\{(.*)\}", st, re.S)
        if m:  # SpikeTrap slam: if (y<608 && vspeed<=0) {vspeed=36 ...}
            body = []
            for s2 in self._split(m.group(2)):
                body.extend(self._stmt(s2, inst, tgt))
            return [("XOP_IF_Y_LT", tgt, float(m.group(1)), len(body) + 1, 0),
                    ("XOP_IF_VY_LE", tgt, 0, len(body), 0)] + body

        m = re.fullmatch(r"if\s*\(\s*x\s*<\s*(-?\d+)\s*\)\s*(.*)", st, re.S)
        if m:
            body = self._stmt(m.group(2), inst, tgt)
            return [("XOP_IF_X_LT", tgt, float(m.group(1)), len(body), 0)] + body

        m = re.fullmatch(r"if\s*\(\s*fire\s*=\s*(\d)\s*\)\s*fire\s*=\s*(\d)",
                         st)
        if m:  # player fire arming chain (rGuy1)
            return [("XOP_IF_PLAYER_FIRE", TGT_PLAYER, float(m.group(1)), 1, 0),
                    ("XOP_SET_FIRE", TGT_PLAYER, float(m.group(2)), 0, 0)]

        # -- simple assignments --------------------------------------------
        m = re.fullmatch(r"\((r\w+_[0-9A-F]{8})\)\.(vspeed|hspeed)\s*=\s*"
                         r"([^\s=]+)", st)
        if m:
            t2 = self.ctx.ent_by_hex(m.group(1).split("_")[-1])
            op = "XOP_SET_VY" if m.group(2) == "vspeed" else "XOP_SET_VX"
            return [(op, t2, _mmf(m.group(3)), 0, 0)]
        m = re.fullmatch(r"(?:other\.)?vspeed\s*=\s*([^\s=]+)", st)
        if m:
            return [("XOP_SET_VY", tgt, _mmf(m.group(1)), 0, 0)]
        m = re.fullmatch(r"(?:other\.)?hspeed\s*=\s*([^\s=]+)", st)
        if m:
            return [("XOP_SET_VX", tgt, _mmf(m.group(1)), 0, 0)]
        m = re.fullmatch(r"image_speed\s*=\s*([^=].*)", st)
        if m:
            return [("XOP_SET_FSPD", tgt, _mmf(m.group(1)), 0, 0)]
        if re.fullmatch(r"visible\s*=\s*(1|true)", st):
            return [("XOP_ARM", tgt, 0, 0, 0)]
        if re.fullmatch(r"on\s*=\s*1", st):
            return [("XOP_SET_STATE", tgt, 1, 0, 0)]
        if re.fullmatch(r"go\s*=\s*1", st):
            return [("XOP_SET_ACTIVE", tgt, 1, 0, 0)]
        if re.fullmatch(r"yes\s*=\s*1", st):
            return [("XOP_SET_P", tgt, 7, 1, 0)]
        if re.fullmatch(r"lase\s*=\s*1", st):
            return [("XOP_SET_STATE", tgt, 1, 0, 0)]
        if re.fullmatch(r"rotato\s*=\s*1", st):
            return [("XOP_SET_STATE", tgt, 2, 0, 0)]
        if re.fullmatch(r"active\s*=\s*(1|true)", st):
            return [("XOP_SET_ACTIVE", tgt, 1, 0, 0),
                    ("XOP_SET_STATE", tgt, 1, 0, 0)]
        if re.fullmatch(r"silent\s*=\s*1", st):
            return []                          # sound suppression only
        if re.fullmatch(r"in_range\s*=\s*(true|1)", st):
            return [("XOP_SET_STATE", tgt, 1, 0, 0)]
        m = re.fullmatch(r"spd\s*=\s*(.+)", st)
        if m:
            # FallingSpike spd: p[2] holds the fall vspeed magnitude
            return [("XOP_SET_P", tgt, 2, _mmf(m.group(1)), 0)]
        if re.fullmatch(r"instance_destroy\(\)", st):
            return [("XOP_DESTROY", tgt, 0, 0, 0)]
        if re.fullmatch(r"event_user\(0\)", st):
            return [("XOP_EVENT", tgt, 0, 0, 0)]
        if re.fullmatch(r"alarm\[0\]\s*=\s*-?1", st):
            return [("XOP_SET_TIMER", tgt, 0, 0, 0)]
        if re.fullmatch(r"image_index\s*=\s*image_number\s*-\s*1", st):
            return [("XOP_LAST_FRAME", tgt, 0, 0, 0)]
        m = re.fullmatch(
            r"(?:i\s*=\s*)?\(?instance_create\(([^,]+),([^,]+),(\w+)\)\)?"
            r"(\s*\.\s*image_xscale\s*=\s*-1)?"
            r"((?:\s*;?\s*i\.go\s*=\s*1)?)\s*", st, re.S)
        if m:
            cls_name = m.group(3)
            if self.ctx.is_excluded_class(cls_name):
                return []                      # boss/visual spawn
            xe = m.group(1).replace("x", f"({inst.x})")
            ye = m.group(2).replace("y", f"({inst.y})").replace(
                "x", f"({inst.x})")
            x = _fold(xe)
            y = _fold(ye)
            tmpl = self.ctx.template_for(cls_name,
                                         flip=bool(m.group(4)),
                                         go="go=1" in (m.group(5) or ""))
            return [("XOP_SPAWN", TGT_NONE, tmpl, x, y)]
        m = re.fullmatch(r"room_goto\((\w+)\)", st)
        if m:
            room = self.ctx.room_index.get(m.group(1))
            if room is None:
                raise ConversionError(f"room_goto target {m.group(1)}")
            return [("XOP_GOTO_ROOM", TGT_NONE, room, -1, 0)]
        m = re.fullmatch(r"(\w+)\.blk_spd\s*=\s*1\s*/\s*(\d+)", st)
        if m:  # FactoryYokuController.blk_spd = 1/N -> p[7]
            return [("XOP_SET_P", TGT_CLS0 - C["XB_FACTORYCTL"], 7,
                     1.0 / float(m.group(2)), 0)]
        m = re.fullmatch(r"(\w+)\.active\s*=\s*0", st)
        if m:  # QuickLaserTimer.active=0
            return [("XOP_SET_ACTIVE", TGT_CLS0 - C["XB_QLTIMER"], 0, 0, 0)]
        m = re.fullmatch(r"global\.(\w+)\s*=\s*(\d+)", st)
        if m:
            name, val = m.group(1), int(m.group(2))
            if name == "castleboost":
                return [("XOP_SPAWNBOOST", TGT_NONE, -24, 0, 0)]
            if name == "factory_ceiling_flag":
                ops = []
                if val == 1:
                    ops.append(("XOP_DESTROY",
                                TGT_CLS0 - C["XB_CONDSOLID"], 0, 0, 0))
                    ops.append(("XOP_DESTROY",
                                TGT_CLS0 - C["XB_RYU"], 0, 0, 0))
                ops.append(("XOP_EVENT",
                            TGT_CLS0 - C["XB_BUTTON"], 0, 0, 0))
                return ops
            raise ConversionError(f"unknown global side effect {st!r}")
        # GML allows space-separated statement sequences: split and retry
        parts = re.split(
            r"(?<=[\w)\]])[ \t]+(?=(?:visible|vspeed|hspeed|active|on|go|"
            r"yes|lase|rotato|spd|image_index|image_speed|alarm\[|"
            r"event_user|instance_create|instance_destroy|room_goto|i=|"
            r"\w+\.active|\w+\.blk_spd|with\s*\(|"
            r"\(r\w+_[0-9A-F]{8}\)\.))",
            st)
        if len(parts) > 1:
            ops = []
            for part in parts:
                ops.extend(self._stmt(part, inst, tgt))
            return ops
        raise ConversionError(
            f"unmatched trigger statement {st!r} "
            f"(room {self.ctx.rname}, instance {inst.id_hex})")


# ---------------------------------------------------------------------------
# Class taxonomy for the 14 gameplay rooms.
# ---------------------------------------------------------------------------

#: purely visual / audio classes (no player-relevant collision or effect for
#: the canonical Kid character) — excluded with this justification
VISUAL_CLASSES = {
    "CastlevaniaSkybox", "FactorySkybox", "FortressSkybox", "GraveyardSkybox",
    "GuySkybox", "KraidSkybox", "RoadSkybox", "RoadSkybox2", "RoadSkybox3",
    "RoadStar", "decoGameover", "decoKumo3", "decoKumoLayer", "decoStar",
    "kumoLeft", "kumoRight", "GutsStarLarge", "GutsStarMedium",
    "GutsStarSmall", "MoonBigDeco", "PlayerSign", "WonSign", "Bosnwentr",
    "StaticEgg", "SpinningBirdoFloor", "SpinningFortBrick", "WallCrack",
    "ZeldaHearts", "MotherBrainPlatform", "musicChanger",
    "CampingNoobs", "AndDownIGo", "RunBoshy",       # Boshy-only sound gags
    "blockFake",       # reveal effect; its overlapping solids are removed
    "EntranceController", "EntranceStatue1", "EntranceStatue2",
    "EntranceStatue3", "EntranceStatue4", "EntranceStatue5",
    "EntranceStatue6", "TysonReferee",
    "secret1trophy", "secret2trophy", "secret3trophy", "secret4trophy",
    "secret5trophy", "secret6trophy",
    "JumpRefresher",   # source: destroyed unless char==Boshy (Kid: absent)
    "MechaWarning",    # arena siren+music cue: draw/sound only, no gameplay
    "TysonStar",       # intro deco star drop (no collision events)
    "Samus",           # escape cameo: path'd sprite, no gameplay events
    "DracGlassShard", "DracSplosion", "DracOrbiterGhost", "EctoParticle",
    "blood", "partFire", "partEntrance", "MagicExplosion", "MagicSmoke",
    "Glass1", "Glass2", "Glass3", "Glass4", "Glass5",   # rGuyBoss panes
    "GlAsshole", "GuyDarkness", "KidSpin", "prtGuyGlass",
    "DeadGuy", "DeadGuyBrow", "DeadGuyMouth", "EndingGun1", "EndingKid1",
    "EndingKid2", "EndingSkybox", "EndingSkybox2",   # rEnding tableau
    "DeadBugz", "VicDeader", "VicBlood", "TourianDebris",
    "DestroyedBlock",
    "saveVeryEvil",    # settings("evilsaves") gated (default off)
    "PlayerMetroided", "CreditsMetroid", "FireGlow",
    # cosmetic runtime spawns (no collision events; debris/particles/text)
    "DestroyedPlatform", "DestroyedSpike", "DestroyedBlock", "DeadBugz",
    "MedusaDead", "NinjaExplosion", "partFire", "partWind", "partEntrance",
    "blood", "bloodEmitter", "SnifitDead", "SpaghettioDestroyed",
    "KamekSparkle", "TourianTurretBulletSplash", "SniperDead", "gameOver",
    "OwataParticle", "OwataPlatform", "Gastly", "BoshyQuote", "BoshyBlood",
    "VicBlood", "OwataBlood", "OwataIn",
}

#: boss / secret-battle objects — justified exceptions this milestone
#: classes whose instances belong to boss content.  After the full-game
#: milestone every one of them is IMPLEMENTED (the set only marks them
#: for the coverage report's boss column); none is excluded any more.
BOSS_CLASSES = {
    "Tyson", "TysonBrick", "TysonDoor", "TysonDoorTrigger",
    "Dragon", "DragonBlock", "DragonMarker", "DragonMarker2", "RoadMoon",
    "MommyThinker", "TourianBarrier",
    "VicViper", "GradiusBoss", "GradiusBugz", "GradiusDrones",
    "GradiusMarker", "Sinistar", "ArkaBall", "ArkaBrick", "ArkaBrickShort",
    "ArkaPlatform", "BowserFireClassic", "Kamek", "Playstation",
    "BossTeleporter", "OrbBirdo", "OrbMother",   # handled separately below
    "Higger",
}
# Of BOSS_CLASSES, these are IMPLEMENTED (either non-boss interactive or
# ported bosses); after the full-game milestone that is the whole set.
IMPLEMENTED_ANYWAY = set(BOSS_CLASSES)

#: classes the STATIC converter already imported
STATIC_CLASSES = {
    "block", "blockNotMerge", "blockMini", "spikeUp", "spikeDown",
    "spikeLeft", "spikeRight", "blockKill", "saveMedium", "saveHard",
    "saveVeryHard", "warp", "playerStart",
}

#: static solid classes added by the exact pass (solid=1 in the source)
EXTRA_SOLID_CLASSES = {"Torizo", "blockYoku", "blockYokuTile", "TextBlock"}


def _spike_variant(name):
    return {"FallingSpike": (4, 0, 10, 1, 2),
            "FallingSpike10frame": (10, 0, 10, 1, 2),
            "FallingSpike10frameUp": (10, 0, -10, 1, 2),
            "FakeFallingSpike": (10 ** 9, 0, 0, 1, 4),
            }.get(name)


# ---------------------------------------------------------------------------
# Room conversion context
# ---------------------------------------------------------------------------

class RoomCtx:
    def __init__(self, build, rname):
        self.build = build
        self.proj = build.proj
        self.masks = build.masks
        self.room_index = build.room_index
        self.rname = rname
        self.src = build.proj.rooms[rname]
        self.xents: list[dict] = []
        self._hex_to_ent: dict[str, int] = {}
        self.deferred: list[tuple] = []     # (fn, args) run after all ents

    # -- entity emission ----------------------------------------------------
    def add(self, cls, x, y, *, mask=0xFFFF, xs=1.0, ys=1.0, flags=0,
            p=None, inst=None, note=""):
        e = {"cls": C[cls] if isinstance(cls, str) else cls,
             "mask": mask, "x": float(x), "y": float(y),
             "xs": float(xs), "ys": float(ys),
             "tag": len(self.xents), "flags": int(flags),
             "p": [float(v) for v in (p or [])] + [0.0] * (10 - len(p or [])),
             "link": -1,
             "provenance": {"source_room": self.rname,
                            "source_object": inst.object if inst else note,
                            "source_instance": inst.id_hex if inst else None}}
        self.xents.append(e)
        if inst is not None and inst.id_hex not in self._hex_to_ent:
            self._hex_to_ent[inst.id_hex] = e["tag"]
        return e["tag"]

    def ent_by_hex(self, hex_id):
        if hex_id not in self._hex_to_ent:
            raise ConversionError(
                f"{self.rname}: reference to instance {hex_id} that produced "
                f"no entity")
        return self._hex_to_ent[hex_id]

    def class_of_object(self, obj_name):
        cls = self.build.class_for_object(obj_name)
        if cls is None:
            raise ConversionError(f"no behavior class for object {obj_name}")
        return cls

    def is_excluded_class(self, obj_name):
        return (obj_name in VISUAL_CLASSES or
                (obj_name in BOSS_CLASSES and
                 obj_name not in IMPLEMENTED_ANYWAY))

    def template_for(self, cls_name, flip=False, go=False):
        return self.build.template_for(cls_name, flip=flip, go=go)

    # geometric queries over SOURCE instances (compile-time resolution)
    def _inst_bbox(self, inst):
        o = self.proj.objects[inst.object]
        spr = self.proj.sprites.get(o.mask or o.sprite)
        p = spr.props if spr else {}
        ox, oy = float(p.get("origin_x", 0)), float(p.get("origin_y", 0))
        bl, bt = float(p.get("bbox_left", 0)), float(p.get("bbox_top", 0))
        br, bb = float(p.get("bbox_right", 31)), float(p.get("bbox_bottom", 31))
        roomvars = {"room_width": float(self.src.width),
                    "room_height": float(self.src.height)}
        xs, ys = _inst_scale(inst, roomvars)
        x0 = inst.x + (bl - ox) * xs
        x1 = inst.x + (br + 1 - ox) * xs
        y0 = inst.y + (bt - oy) * ys
        y1 = inst.y + (bb + 1 - oy) * ys
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        return x0, y0, x1 - 1, y1 - 1

    def overlapping_of_class(self, trig_inst, cls_name, dx=0.0,
                             all_hits=False):
        tx0, ty0, tx1, ty1 = self._inst_bbox(trig_inst)
        tx0 += dx
        tx1 += dx
        hits = []
        for other in self.src.instances:
            if other.object != cls_name:
                continue
            if other.id_hex not in self._hex_to_ent:
                continue
            ox0, oy0, ox1, oy1 = self._inst_bbox(other)
            if ox1 >= tx0 and ox0 <= tx1 and oy1 >= ty0 and oy0 <= ty1:
                hits.append(self._hex_to_ent[other.id_hex])
        return hits if all_hits or len(hits) != 1 else hits


# ---------------------------------------------------------------------------
# The exact-layer builder
# ---------------------------------------------------------------------------

def _cc(inst, roomvars):
    if getattr(inst, "_cc_parsed", None) is None:
        vals = {}
        if inst.creation_code:
            code = inst.creation_code
            for m in re.finditer(
                    r"\b(\w+)\s*=\s*(\"[^\"]*\"|mmf_speed\(-?\d+\)|"
                    r"room_width\s*/\s*\d+|-?\d+\s*/\s*\d+|"
                    r"-?\d+(?:\.\d+)?|true|false|\w+)\s*;?", code):
                k, v = m.group(1), m.group(2).strip()
                if v.startswith('"'):
                    vals[k] = v.strip('"')
                elif v == "true":
                    vals[k] = 1.0
                elif v == "false":
                    vals[k] = 0.0
                elif re.fullmatch(r"-?\d+(?:\.\d+)?", v):
                    vals[k] = float(v)
                elif re.fullmatch(r"mmf_speed\(-?\d+\)", v):
                    vals[k] = float(re.findall(r"-?\d+", v)[0]) / 8.0
                elif re.fullmatch(r"-?\d+\s*/\s*\d+", v):
                    a, b = re.findall(r"-?\d+", v)
                    vals[k] = float(a) / float(b)
                elif re.fullmatch(r"room_width\s*/\s*\d+", v):
                    vals[k] = roomvars["room_width"] / float(
                        re.findall(r"\d+", v)[-1])
                else:
                    vals[k] = v
        inst._cc_parsed = vals
    return inst._cc_parsed


def _inst_scale(inst, roomvars):
    cc = _cc(inst, roomvars)
    xs = inst.xscale
    ys = inst.yscale
    if isinstance(cc.get("image_xscale"), float):
        xs *= cc["image_xscale"]
    if isinstance(cc.get("image_yscale"), float):
        ys *= cc["image_yscale"]
    return xs, ys


class ExactBuild:
    def __init__(self, source_root, proj, ir, room_index):
        self.source_root = source_root
        self.proj = proj
        self.ir = ir
        self.room_index = room_index
        self.masks = MaskTable(source_root, proj)
        self.asm = OpAsm()
        self.keys: list[float] = []
        self.templates: list[dict] = []
        self._tmpl_key: dict[tuple, int] = {}
        self.coverage = {"implemented": Counter(), "static": Counter(),
                         "implemented_boss": Counter(),
                         "excluded_visual": Counter(),
                         "excluded_boss": Counter(),
                         "trigger_programs": 0,
                         "boss_exception_notes": {}}
        self.xrooms: list[dict] = []

    # -- pools ---------------------------------------------------------------
    def add_keys(self, floats) -> tuple[int, int]:
        off = len(self.keys)
        self.keys.extend(float(v) for v in floats)
        return off, len(floats)

    def mask(self, sprite, per_frame=None):
        return self.masks.get(sprite, per_frame)

    # -- spawn templates -----------------------------------------------------
    def template(self, cls, mask, xs=1.0, ys=1.0, flags=0, p=None,
                 key=None) -> int:
        k = key or (cls, mask, xs, ys, flags, tuple(p or []))
        if k in self._tmpl_key:
            return self._tmpl_key[k]
        idx = len(self.templates)
        self.templates.append({
            "cls": C[cls] if isinstance(cls, str) else cls,
            "mask": mask, "xs": xs, "ys": ys, "flags": flags,
            "p": [float(v) for v in (p or [])] + [0.0] * (10 - len(p or []))})
        self._tmpl_key[k] = idx
        return idx

    def template_for(self, cls_name, flip=False, go=False):
        """Template for a runtime-spawned source class."""
        from . import bosses as _b
        t = _b.template_for(self, cls_name)
        if t is not None:
            return t
        M = self.mask
        if cls_name == "HoverGunner":
            return self.template("XB_HOVERGUNNER", M("sprTurret"),
                                 flags=XEF_SHOOTABLE,
                                 p=[1 if go else 0,
                                    self.template_for("HoverShot")],
                                 key=("HoverGunner", go))
        if cls_name == "HoverShot":
            return self.template("XB_HOVERSHOT", M("sprTurretBullet"),
                                 flags=XEF_KILLER, key=("HoverShot",))
        if cls_name == "TourianTurretBullet":
            return self.template("XB_HOVERSHOT",
                                 M("sprMetroidTurretBullet"),
                                 flags=XEF_KILLER, key=("TTB",))
        if cls_name == "BIRD":
            return self.template("XB_BIRD", M("sprBIRD"),
                                 xs=1.5 if not flip else -1.5, ys=1.5,
                                 flags=XEF_SHOOTABLE, key=("BIRD", flip))
        if cls_name == "Ghoul":
            return self.template("XB_GHOUL", M("sprGhoul"),
                                 flags=XEF_SHOOTABLE, key=("Ghoul",))
        if cls_name == "DumbBugz":
            return self.template("XB_DUMBBUGZ", M("sprDumbBugz"),
                                 xs=-1.0 if flip else 1.0,
                                 flags=XEF_KILLER | XEF_SHOOTABLE |
                                 XEF_FORCE_ACTIVE,
                                 key=("DumbBugz", flip))
        if cls_name == "Metroid":
            return self.template("XB_METROID", M("sprMetroid"),
                                 key=("Metroid",))
        if cls_name == "Spaghettio":
            return self.template("XB_SPAG", M("sprSpaghettios"),
                                 flags=XEF_KILLER | XEF_SHOOTABLE,
                                 key=("Spag",))
        if cls_name == "RollingRocks":
            return self.template("XB_ROLLROCK", M("sprRollingRocks"),
                                 flags=XEF_KILLER, key=("Rock",))
        if cls_name == "Playstation":
            return self.template("XB_PLAYSTATION", M("sprKamekPlaystation"),
                                 flags=XEF_KILLER, key=("PS",))
        if cls_name == "KillPill":
            return self.template("XB_KILLPILL", M("sprKillPill"),
                                 xs=18, ys=18,
                                 flags=XEF_KILLER | XEF_FORCE_ACTIVE,
                                 key=("KillPill",))
        if cls_name == "GutsMan":
            return self.template("XB_GUTSMAN", M("sprGutsFall"),
                                 key=("GutsMan",))
        if cls_name == "KillPlane":
            return self.template("XB_KILLPLANE", M("sprKillPlane"),
                                 xs=18.75, ys=17.4,
                                 flags=XEF_KILLER | XEF_FORCE_ACTIVE,
                                 key=("KillPlane",))
        if cls_name == "ErrorTrap":
            return self.template("XB_ERRORTRAP", M("sprError"),
                                 flags=XEF_FORCE_ACTIVE, key=("ErrorTrap",))
        if cls_name == "MedusaHead":
            return self.template("XB_MEDUSA", M("sprMedusa"),
                                 flags=XEF_SHOOTABLE, key=("Medusa",))
        if cls_name == "SnifitBullet":
            return self.template("XB_SNIFITBULLET", M("sprBulletBill"),
                                 flags=XEF_KILLER, key=("SnifitB",))
        if cls_name == "CUTE_KITTY_BOOM":
            return self.template("XB_BOOM", M("sprDraculaExplosion"),
                                 xs=20, ys=20, flags=XEF_KILLER,
                                 key=("Boom",))
        if cls_name == "MoonBigFall":
            off, n = self._moonbig_keys()
            return self.template("XB_MOONBIG", M("sprMoonBig"),
                                 xs=3.3, ys=3.3,
                                 flags=XEF_KILLER | XEF_FORCE_ACTIVE,
                                 p=[0, off, n // 2],
                                 key=("MoonBig",))
        if cls_name == "block":
            return self.template("XB_TETBLOCK",
                                 self.masks.rect_mask(32, 32),
                                 flags=XEF_SOLID, key=("block32",))
        if cls_name == "tetrisBlock":
            return self.template("XB_TETBLOCK",
                                 self.masks.rect_mask(32, 32),
                                 flags=XEF_SOLID, key=("tetblock",))
        if cls_name == "deliciousFruit":
            return self.template("XB_FRUIT", M("sprCherry"),
                                 flags=XEF_KILLER, key=("Fruit",))
        if cls_name == "secret4":
            return self.template("XB_SECRET", M("sprSecret4"),
                                 p=[SECRET_FLAGS["secret4"]],
                                 key=("secret4",))
        if cls_name == "FireSometimesUpside":
            return self.template("XB_ANIM_KILLER", M("sprFireMarker"),
                                 ys=-1.0, flags=XEF_KILLER,
                                 p=[0.3, 0, 0, 0, 1, 0, 0, -1, 0, 0],
                                 key=("FireUpside",))
        raise ConversionError(f"no spawn template rule for {cls_name}")

    def class_for_object(self, obj_name):
        return OBJECT_TO_CLASS.get(obj_name)

    def _moonbig_keys(self):
        if not hasattr(self, "_moon_off"):
            pts = _load_path(self.source_root, "pMoonFall")
            trace = sample_path(pts["points"], pts["smooth"], pts["closed"],
                                speed=1.0, max_frames=30000)
            flat = [c for xy in trace for c in xy]
            self._moon_off = self.add_keys(flat)
        return self._moon_off


#: secret pickup flags (gflag bits; orbs use PROGRESSION_FLAGS 1..8)
SECRET_FLAGS = {f"secret{i}": 19 + i for i in range(1, 7)}

#: object -> behavior class (for class-broadcast op targets)
OBJECT_TO_CLASS = {
    "Witch": C["XB_WITCH"], "WitchShadow": C["XB_WITCHSHADOW"],
    "Grabby": C["XB_ANIM_KILLER"], "CatThing": C["XB_CATTHING"],
    "FireChalice": C["XB_FIRECHALICE"],
    "FactorySpinner1": C["XB_SPINNER"], "FactorySpinner2": C["XB_SPINNER"],
    "SniperJohn": C["XB_SNIPER"], "FactoryYokuController": C["XB_FACTORYCTL"],
    "FactoryYoku": C["XB_FACTORYBLOCK"], "SnifitCannon": C["XB_SNIFITCANNON"],
    "Tyson": C["XB_BOSS_TYSON"], "player": -2,
    "MommyThinker": C["XB_BOSS_MOMMY"], "RoadMoon": C["XB_ROADMOON"],
    "Dragon": C["XB_BOSS_DRAGON"], "Sinistar": C["XB_SINISTAR"],
    "FallingCeiling": C["XB_FCEIL"],
    "FallingCeilingSpike": C["XB_FCSPIKE"],
    # rBowserBoss only: the rect-selected spikeDowns are XB_FCEIL ents
    "spikeDown": C["XB_FCEIL"],
    "CycleSpikeUp": C["XB_ANIM_KILLER"], "CycleSpikeDown": C["XB_ANIM_KILLER"],
    "FallingBlockTrap": C["XB_SHAKE_FALL"],
    "FallingSpike10frameUp": C["XB_SHAKE_FALL"],
    "FallingSpike10frame": C["XB_SHAKE_FALL"],
    "FallingSpike": C["XB_SHAKE_FALL"], "FallingCave": C["XB_SHAKE_FALL"],
    "MoonSmall": C["XB_MOONSMALL"],
    "LongForm": C["XB_MOVPLAT"], "Higger": C["XB_HIGGER"],
    "RevealingSpikesUp": C["XB_REVEALING"], "Lonk": C["XB_LONK"],
    "QuickLaserTimer": C["XB_QLTIMER"], "Skwee": C["XB_SKWEE"],
    "Samus": -1, "WheelTrap": C["XB_WHEEL"],
    "FallingFort": C["XB_FALLPLAT"], "movingPlatform": C["XB_MOVPLAT"],
    "RealYoku": C["XB_REALYOKU"],
    "RealYokuController": C["XB_REALYOKUCTL"],
    "Ryu": C["XB_RYU"], "FactoryCeiling": C["XB_CONDSOLID"],
    "RyuButton": C["XB_BUTTON"], "PlatformReset": C["XB_BUTTON"],
}


def _load_path(source_root, name):
    d = os.path.join(source_root, "paths", name)
    meta = {}
    with open(os.path.join(d, "path.txt")) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                meta[k] = v
    pts = []
    with open(os.path.join(d, "points.txt")) as f:
        for line in f:
            line = line.strip()
            if line:
                x, y, sp = line.split(",")
                pts.append((float(x), float(y), float(sp)))
    return {"points": pts, "smooth": meta.get("connection") == "1",
            "closed": meta.get("closed") == "1"}


# ---------------------------------------------------------------------------
# tetris timeline simulation (rKraidgiefLair)
# ---------------------------------------------------------------------------

def _parse_gml_arrays(code):
    """movex/movey/rotcw/rotccw/nexts/clear sparse arrays + scalars from
    tetrisController Create_0."""
    arrays = {"movex": {}, "movey": {}, "rotcw": {}, "rotccw": {},
              "nexts": {}, "clear": {}}
    scalars = {}
    for m in re.finditer(r"(movex|movey|rotcw|rotccw|nexts|clear)"
                         r"\[(\d+)\]\s*=\s*(-?\w+)", code):
        arr, idx, val = m.group(1), int(m.group(2)), m.group(3)
        arrays[arr][idx] = val
    for m in re.finditer(r"^(\w+)\s*=\s*(-?\d+)\s*$", code, re.M):
        scalars[m.group(1)] = int(m.group(2))
    return arrays, scalars


#: tetrimino block layouts per (type, angle) — objects/tetrimino.gml
#: Other_10, offsets relative to the tetrimino origin.
TETROMINO = {
    ("l", 0): [(-32, -64), (-32, -32), (-32, 0), (0, 0)],
    ("l", 1): [(32, -32), (0, -32), (-32, -32), (-32, 0)],
    ("l", 2): [(-32, -64), (0, -64), (0, -32), (0, 0)],
    ("z", 0): [(0, -32), (0, 0), (-32, 0), (-32, 32)],
    ("z", 1): [(-64, 0), (-32, 0), (-32, 32), (0, 32)],
    ("t", 0): [(-32, -32), (-32, 0), (0, 0), (-32, 32)],
    ("t", 1): [(-64, 0), (-32, 0), (-32, 32), (0, 0)],
    ("t", 2): [(-32, -32), (-32, 0), (-64, 0), (-32, 32)],
    ("t", 3): [(-64, 0), (-32, 0), (-32, -32), (0, 0)],
    ("j", 0): [(0, -64), (0, -32), (-32, 0), (0, 0)],
    ("j", 1): [(-64, -32), (-64, 0), (-32, 0), (0, 0)],
    ("j", 2): [(0, -64), (-32, -64), (-32, -32), (-32, 0)],
    ("i", 0): [(0, -64), (0, -32), (0, 0), (0, 32)],
    ("i", 1): [(-64, -32), (-32, -32), (0, -32), (32, -32)],
    ("o", 0): [(-32, -32), (0, -32), (-32, 0), (0, 0)],
    ("s", 0): [(-32, -32), (-32, 0), (0, 0), (0, 32)],
}
TET_ANGLES = {"l": 3, "z": 2, "t": 4, "j": 3, "i": 2, "o": 1, "s": 1}
TET_NAMES = {1: "i", 2: "t", 3: "s", 4: "l", 5: "j", 6: "o", 7: "z",
             8: "pill"}


def simulate_tetris(code, max_t=3000):
    """Offline simulation of tetrisController + tetrimino + tetrisBlock +
    clear_tetris_rows -> (n_slots, events). Events:
        (t, "show", slot, x, y) / (t, "hide", slot) / (t, "move", slot, x, y)
        (t, "pill",)
    Slots are reused (bounded): 4 for the falling piece + frozen terrain."""
    arrays, _sc = _parse_gml_arrays(code)

    def val(arr, t):
        v = arrays[arr].get(t, 0)
        try:
            return int(v)
        except (TypeError, ValueError):
            return v

    events = []
    free: list[int] = []
    n_slots = [0]
    alive: dict[int, tuple] = {}

    def alloc(x, y, t):
        sid = free.pop() if free else n_slots[0]
        if sid == n_slots[0]:
            n_slots[0] += 1
        alive[sid] = (x, y)
        events.append((t, "show", sid, x, y))
        return sid

    def hide(sid, t):
        events.append((t, "hide", sid))
        alive.pop(sid, None)
        free.append(sid)

    cur = None
    nxt = "l"                       # tetrisController Create: next = l

    def layout():
        return TETROMINO[(cur["type"], cur["angle"])]

    def relayout(t):
        for sid, (dx, dy) in zip(cur["ids"], layout()):
            x, y = cur["x"] + dx, cur["y"] + dy
            alive[sid] = (x, y)
            events.append((t, "move", sid, x, y))

    def create(t, typ):
        nonlocal cur
        if typ == "pill" or typ is None:
            events.append((t, "pill"))
            cur = None
            return
        cur = {"type": typ, "angle": 0, "x": 384, "y": 32,
               "ids": [alloc(384 + dx, 32 + dy, t)
                       for dx, dy in TETROMINO[(typ, 0)]]}

    def move(t, dx, dy):
        if cur is None or (dx == 0 and dy == 0):
            return
        cur["x"] += dx * 32
        cur["y"] += dy * 32
        relayout(t)

    def rotate(t, cw):
        if cur is None:
            return
        n = TET_ANGLES[cur["type"]]
        cur["angle"] = (cur["angle"] + (1 if cw else -1)) % n
        relayout(t)

    def clear_rows(t, n):
        for sid in list(alive):
            if cur is not None and sid in cur["ids"]:
                continue
            x, y = alive[sid]
            y += n * 32
            if y >= 576:
                hide(sid, t)
            else:
                alive[sid] = (x, y)
                events.append((t, "move", sid, x, y))
        if cur is not None:
            relayout(t)

    for t in range(0, max_t):
        mx, my = val("movex", t), val("movey", t)
        move(t, mx or 0, my or 0)
        if val("rotcw", t):
            rotate(t, True)
        if val("rotccw", t):
            rotate(t, False)
        nv = arrays["nexts"].get(t)
        if nv is not None:
            prev = cur
            if prev is not None:
                cur = None          # previous piece freezes (ids stay shown)
            create(t, nxt)
            nv = str(nv)
            nxt = nv if nv in ("i", "t", "s", "l", "j", "o", "z", "pill") \
                else None
        cv = val("clear", t)
        if cv:
            clear_rows(t, cv)
    return n_slots[0], events


# ---------------------------------------------------------------------------
# Per-room emission
# ---------------------------------------------------------------------------

#: static-solid classes rasterized by the exact pass (solid=1 in source)
def _rasterize_solid(build, ctx, ir_room, inst, roomvars):
    """Add a static solid from the instance's (possibly precise) mask."""
    o = build.proj.objects[inst.object]
    spr_name = o.mask or o.sprite
    spr = build.proj.sprites[spr_name]
    p = spr.props
    xs, ys = _inst_scale(inst, roomvars)
    ox, oy = float(p.get("origin_x", 0)), float(p.get("origin_y", 0))
    if int(p.get("collision_shape", 0)) == 1:     # rectangle
        bl, bt = float(p["bbox_left"]), float(p["bbox_top"])
        br, bb = float(p["bbox_right"]), float(p["bbox_bottom"])
        x0 = inst.x + (bl - ox) * xs
        x1 = inst.x + (br + 1 - ox) * xs - 1
        y0 = inst.y + (bt - oy) * ys
        y1 = inst.y + (bb + 1 - oy) * ys - 1
        ir_room["solids"].append([min(x0, x1), min(y0, y1),
                                  max(x0, x1), max(y0, y1)])
        return 1
    # precise: rasterize row spans, scaled (integer pixel coverage)
    n = 0
    for (sy, sx0, sx1) in build.masks.spans(spr_name, 0):
        x0 = inst.x + (sx0 - ox) * xs
        x1 = inst.x + (sx1 + 1 - ox) * xs - 1
        y0 = inst.y + (sy - oy) * ys
        y1 = inst.y + (sy + 1 - oy) * ys - 1
        ir_room["solids"].append([min(x0, x1), min(y0, y1),
                                  max(x0, x1), max(y0, y1)])
        n += 1
    return n


def _merge_solids(solids):
    """Merge vertically-adjacent identical-x rects (rasterized spans)."""
    solids.sort(key=lambda s: (s[0], s[2], s[1]))
    out = []
    for s in solids:
        if out and abs(out[-1][0] - s[0]) < 1e-6 and \
                abs(out[-1][2] - s[2]) < 1e-6 and \
                abs(out[-1][3] + 1 - s[1]) < 1e-6:
            out[-1][3] = s[3]
        else:
            out.append(list(s))
    return out


FIRE_VARIANTS = {
    #        fspd frame0 lo  hi armed maskless die kill touch ping
    "Fire":            (0.5, 0, 0, 10, 0, 1, 0, -1, 0, 0),
    "FireOnce":        (0.2, 0, 0, 0, 0, 0, 1, -1, 0, 0),
    "FireShort":       (0.5, 0, 0, 8, 0, 0, 0, -1, 0, 0),
    "FireSometimes":   (0.3, 0, 0, 0, 0, 0, 0, -1, 0, 0),
    "FirePermanent":   (0.5, 8, 0, 10, 1, 0, 0, -1, 0, 0),
    "FireShortPermanent": (0.5, 6, 0, 8, 1, 0, 0, -1, 0, 0),
    "FireSometimesPermanent": (0.3, 0, 0, 0, 1, 0, 0, -1, 0, 0),
    "FireSometimesUpside": (0.3, 0, 0, 0, 1, 0, 0, -1, 0, 0),
}

MARKER_KINDS = {
    "BounceUp": XM_BOUNCE_UP, "BounceDown": XM_BOUNCE_DOWN,
    "BounceLeft": XM_BOUNCE_LEFT, "BounceRight": XM_BOUNCE_RIGHT,
    "blockNise": XM_BLOCKNISE, "KumoStopper": XM_KUMOSTOP,
    "DumpMoment": XM_DUMP, "BulletTrigger": XM_BULLETTRIGGER,
    "CartStopper": XM_CARTSTOP, "MedusaModifier": XM_MEDUSAMOD,
    "SoftlockBlocker": XM_SOFTLOCK, "FirstRoomSpikeWall": XM_FRSW,
}

MARKER_SPRITES = {
    "BounceUp": "sprBouncerUp", "BounceDown": "sprBouncerDown",
    "BounceLeft": "sprBouncerLeft", "BounceRight": "sprBouncerRight",
    "blockNise": "sprBlockNise", "KumoStopper": "sprBlockNise",
    "DumpMoment": "sprBlockNise", "BulletTrigger": "sprControllerMMF2",
    "CartStopper": "sprBlockNise", "MedusaModifier": "sprBlockNise",
    "SoftlockBlocker": "sprSoftlock", "FirstRoomSpikeWall": "sprBlockNise",
}


def emit_room(build: ExactBuild, rname: str, ir_room: dict) -> dict:
    """Emit the exact-layer entities/programs for one gameplay room."""
    proj = build.proj
    src = proj.rooms[rname]
    roomvars = {"room_width": float(src.width),
                "room_height": float(src.height)}
    ctx = RoomCtx(build, rname)
    M = build.mask
    cov = build.coverage
    camera = XCAM_NONE
    triggers = []       # (inst, cc) processed after all entities exist
    enter_ops = (0, 0)

    # instance ids referenced by trigger programs: statically-imported
    # spikes among them must become movable killer entities instead
    referenced = set()
    for inst in src.instances:
        if inst.object in ("trigger", "warp") and inst.creation_code:
            referenced.update(
                m.split("_")[-1] for m in
                re.findall(r"r\w+_[0-9A-F]{8}", inst.creation_code))
    if rname == "rKraidgiefBoss":
        # the boss destroys the spike floor on death (and the won-arena
        # teardown clears it), so the row cannot stay in the static grid
        referenced.update(i.id_hex for i in src.instances
                          if i.object == "spikeUp")
    if rname == "rGuyBoss":
        # GuyFirst's intro slides the spikeRight wall shut (they get
        # tag 77 below so the boss can move them by class)
        referenced.update(i.id_hex for i in src.instances
                          if i.object == "spikeRight")
    fceil_spikes = set()
    if rname == "rBowserBoss":
        # the arena trigger gives spikeDown in (832,192)-(1568,224) the
        # FallingCeiling group's vspeed: those become XB_FCEIL entities
        fceil_spikes = {i.id_hex for i in src.instances
                        if i.object == "spikeDown" and
                        832 <= i.x <= 1568 and 192 <= i.y <= 224}
        referenced |= fceil_spikes

    # blockFake regions: overlapping blocks were removed at compile time
    fake_boxes = []
    for inst in src.instances:
        if inst.object == "blockFake":
            xs, ys = _inst_scale(inst, roomvars)
            fake_boxes.append((inst.x, inst.y,
                               inst.x + 32 * xs - 1, inst.y + 32 * ys - 1))

    for inst in src.instances:
        obj = inst.object
        cc = _cc(inst, roomvars)
        xs, ys = _inst_scale(inst, roomvars)
        x, y = inst.x, inst.y

        if obj in STATIC_CLASSES:
            # statically-imported spikes that trigger programs move become
            # XB_BOLT killer entities (precise spike mask, launchable)
            if obj in ("spikeUp", "spikeDown", "spikeLeft", "spikeRight") \
                    and inst.id_hex in referenced and cc.get("dest") != 1.0:
                ch = {"spikeUp": "^", "spikeDown": "v",
                      "spikeLeft": "<", "spikeRight": ">"}[obj]
                tx, ty = int(x) // TILE, int(y) // TILE
                rows = ir_room["tiles"]
                if (0 <= ty < len(rows) and 0 <= tx < len(rows[0]) and
                        rows[ty][tx] == ch):
                    rows[ty] = rows[ty][:tx] + "." + rows[ty][tx + 1:]
                else:
                    ir_room["killers"] = [
                        k for k in ir_room["killers"]
                        if not (abs(k["x0"] - x) < 33 and
                                abs(k["y0"] - y) < 33)]
                spr = proj.objects[obj].sprite
                pv = None
                cls_name = "XB_BOLT"
                if rname == "rGuyBoss" and obj == "spikeRight":
                    pv = [0, 0, 0, 0, 0, 0, 0, 77]   # GuyFirst's wall
                if inst.id_hex in fceil_spikes:
                    cls_name = "XB_FCEIL"            # ceiling group spike
                ctx.add(cls_name, x, y, mask=M(spr), xs=xs, ys=ys,
                        flags=XEF_KILLER, p=pv, inst=inst)
                cov["implemented"][obj] += 1
                continue
            # spikeUp with dest=1 becomes a destructible-linked killer xent
            if obj == "spikeUp" and cc.get("dest") == 1.0:
                # remove the static import (tile or killer record)
                tx, ty = int(x) // TILE, int(y) // TILE
                rows = ir_room["tiles"]
                if rows[ty][tx] == "^":
                    rows[ty] = rows[ty][:tx] + "." + rows[ty][tx + 1:]
                else:
                    ir_room["killers"] = [
                        k for k in ir_room["killers"]
                        if not (abs(k["x0"] - x) < 1 and abs(k["y0"] - y) < 1)]
                tag = ctx.add("XB_KILLER", x, y, mask=M("sprSpikeUp"),
                              xs=xs, ys=ys, flags=XEF_KILLER, inst=inst,
                              p=[0, 0, 0, 0, 0, 0, 0, 0, 0])
                ctx.deferred.append(("dest_spike", tag, inst))
                cov["implemented"][obj] += 1
            continue
        if obj in ROOM_CAMERA:
            camera = ROOM_CAMERA[obj]
            if camera == XCAM_HARD and rname == "rMetroid":
                camera = XCAM_HARD_METROID
            cov["implemented"][obj] += 1
            continue
        if obj in VISUAL_CLASSES:
            cov["excluded_visual"][obj] += 1
            continue
        if obj in BOSS_CLASSES and obj not in IMPLEMENTED_ANYWAY:
            cov["excluded_boss"][obj] += 1
            continue

        if obj in MARKER_KINDS:
            ctx.add("XB_MARKER", x, y, mask=M(MARKER_SPRITES[obj]),
                    xs=xs, ys=ys, p=[MARKER_KINDS[obj]], inst=inst)
            cov["implemented"][obj] += 1
            continue

        if obj in FIRE_VARIANTS:
            p = list(FIRE_VARIANTS[obj])
            fy, fys = y, ys
            if obj == "FireOnce":
                fy -= 2                          # Create: y -= 2
            if obj == "FireSometimesUpside":
                fy += 32
                fys = -ys
            ctx.add("XB_ANIM_KILLER", x, fy, mask=M("sprFireMarker"),
                    xs=xs, ys=fys, flags=XEF_KILLER, p=p, inst=inst)
            cov["implemented"][obj] += 1
            continue

        emitted = _emit_class(build, ctx, ir_room, inst, obj, x, y, xs, ys,
                              cc, roomvars, triggers)
        if emitted is None:
            raise ConversionError(
                f"{rname}: object class {obj!r} is neither implemented nor "
                f"excluded with justification (coverage gate)")
        if emitted is True:            # "static" is tallied in cov["static"]
            from . import bosses as _b
            key = ("implemented_boss" if rname in _b.BOSS_ROOMS
                   else "implemented")
            cov[key][obj] += 1

    # deferred cross-links
    for kind, *args in ctx.deferred:
        if kind == "dest_spike":
            tag, inst = args
            hits = ctx.overlapping_of_class(inst, "blockTrapDestructible",
                                            all_hits=True)
            below = None
            for h in hits:
                e = ctx.xents[h]
                if e["y"] > inst.y:
                    below = h
            if below is not None:
                ctx.xents[tag]["p"][8] = float(below + 1)
        elif kind == "link":
            tag, other = args
            ctx.xents[tag]["link"] = other

    # blockFake: overlapping real blocks are destroyed at room start
    for (fx0, fy0, fx1, fy1) in fake_boxes:
        ir_room["solids"] = [
            s2 for s2 in ir_room["solids"]
            if not (s2[2] >= fx0 and s2[0] <= fx1 and
                    s2[3] >= fy0 and s2[1] <= fy1)]
        rows = ir_room["tiles"]
        for ty in range(int(fy0) // TILE, int(fy1) // TILE + 1):
            for tx in range(int(fx0) // TILE, int(fx1) // TILE + 1):
                if 0 <= ty < len(rows) and 0 <= tx < len(rows[0]) and \
                        rows[ty][tx] == "#":
                    rows[ty] = rows[ty][:tx] + "." + rows[ty][tx + 1:]

    # trigger programs (after every entity has an index)
    tc = TriggerCompiler(ctx)
    for inst, cc2 in triggers:
        _emit_trigger(build, ctx, tc, inst, cc2, roomvars)
        cov["trigger_programs"] += 1
    _finish_deferred(build, ctx)

    from . import bosses as _b
    if rname in _b.BOSS_ROOMS or rname == "rGuy1":
        enter_ops = _b.enter_ops_for(build, rname)
    if rname == "rGuyBoss" and camera == XCAM_NONE:
        # no camera object in source: the world's default per-screen snap
        # (the head fight drops the player to the lower screen)
        camera = XCAM_HARD

    return {"name": rname, "xents": ctx.xents, "camera": camera,
            "always_active": 1 if rname == "rGuyLabyrinth" else 0,
            "enter_ops": list(enter_ops),
            "kind": 1 if rname == _b.ENDING_ROOM else 0}


def _emit_class(build, ctx, ir_room, inst, obj, x, y, xs, ys, cc, roomvars,
                triggers):
    """Emit entities for one instance. True = implemented; None = unknown."""
    M = build.mask
    add = ctx.add

    # ---- static solid additions -----------------------------------------
    if obj in EXTRA_SOLID_CLASSES:
        _rasterize_solid(build, ctx, ir_room, inst, roomvars)
        build.coverage["static"][obj] += 1
        return "static"
    if obj == "ZeldaCollision":
        # Create: image_xscale = room_width/256, yscale = room_height/480
        inst.xscale = roomvars["room_width"] / 256.0
        inst.yscale = roomvars["room_height"] / 480.0
        n = _rasterize_solid(build, ctx, ir_room, inst, roomvars)
        ir_room["solids"] = _merge_solids(ir_room["solids"])
        build.coverage["static"][obj] += n and 1
        return "static"

    # ---- triggers (deferred) --------------------------------------------
    if obj == "trigger":
        triggers.append((inst, cc))
        add("XB_TRIGGER", x, y, mask=M("maskTrigger"), xs=xs, ys=ys,
            p=[-1, -1, -1, TGT_NONE, 0, 0, 0], inst=inst)
        return True
    if obj == "triggerLockControls":
        add("XB_LOCKCONTROLS", x, y, mask=M("sprBlockSlip"), xs=xs, ys=ys,
            inst=inst)
        return True

    # ---- killers / traps -------------------------------------------------
    simple_killers = {
        "trapStar": "sprDecoStar", "Snifit": "sprSnifit",
        "Turbine": "sprTurbine", "EggHitbox": "sprEggHitbox",
        "BoltTrap": None, "FactoryCeiling": None,
    }
    if obj == "trapStar":
        add("XB_KILLER", x, y, mask=M("sprDecoStar"), xs=xs, ys=ys,
            flags=XEF_KILLER, p=[0.2, 0, 0, 1], inst=inst)
        return True
    if obj == "Snifit":
        add("XB_KILLER", x, y, mask=M("sprSnifit"), xs=xs, ys=ys,
            flags=XEF_KILLER, p=[0, 0, 0, 0, 0, 0, 0, 1], inst=inst)
        return True
    if obj == "Turbine":
        add("XB_KILLER", x, y, mask=M("sprTurbine"), xs=xs, ys=ys,
            flags=XEF_KILLER, p=[0, 0, 0, 0, 0, 0, 0, 2], inst=inst)
        return True
    if obj == "EggHitbox":
        add("XB_KILLER", x, y, mask=M("sprEggHitbox"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "BoltTrap":
        add("XB_BOLT", x, y, mask=M("sprBoltTrap"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "ZeldaFire":
        add("XB_KILLER", x, y, mask=M("sprZeldaFire"),
            xs=800 / 256.0, ys=608 / 240.0,
            flags=XEF_KILLER | XEF_MIRROR8, inst=inst)
        return True
    if obj == "ZeldaOldMan":
        add("XB_KILLER", x, y, mask=M("sprZeldaOldMan"),
            xs=800 / 256.0, ys=608 / 240.0, flags=XEF_KILLER, inst=inst)
        return True
    if obj == "ZeldaSword":
        add("XB_KILLER", x, y, mask=M("sprZeldaSword"),
            xs=800 / 256.0, ys=608 / 240.0, flags=XEF_KILLER, inst=inst)
        return True
    if obj in ("CycleSpikeUp", "CycleSpikeDown"):
        spr = "sprCycleSpikeUp" if obj.endswith("Up") else "sprCycleSpikeDown"
        add("XB_ANIM_KILLER", x, y, mask=M(spr), xs=xs, ys=ys,
            flags=XEF_KILLER, p=[0, 0, 0, 0, 1, 0, 0, -1, 0, 0], inst=inst)
        return True
    if obj == "Grabby":
        add("XB_ANIM_KILLER", x, y, mask=M("sprGrabby"), xs=xs, ys=ys,
            flags=XEF_KILLER, p=[0.3, 0, 0, 0, 0, 0, 0, -1, 0, 1],
            inst=inst)
        return True
    if obj == "GraveTrap":
        add("XB_ANIM_KILLER", x, y, mask=M("sprGraveTrap"), xs=xs, ys=ys,
            flags=XEF_KILLER, p=[0.2, 0, 0, 0, 0, 0, 0, 6, 1, 0], inst=inst)
        return True
    if obj in ("FallingSpike", "FallingSpike10frame", "FallingSpike10frameUp",
               "FakeFallingSpike"):
        shake, _vx, vy, both, period = _spike_variant(obj)
        spr = "sprSpikeUp" if obj.endswith("Up") else "sprSpike"
        add("XB_SHAKE_FALL", x, y, mask=M(spr), xs=xs, ys=ys,
            flags=XEF_KILLER, p=[shake, 0, vy, both, period, 0, 0],
            inst=inst)
        return True
    if obj == "FallingCave":
        add("XB_SHAKE_FALL", x, y, mask=M("sprFallingCave"), xs=xs, ys=ys,
            flags=XEF_KILLER, p=[20, 0, 7.5, 0, 2, 0, 0], inst=inst)
        return True
    if obj == "FallingBlockTrap":
        add("XB_SHAKE_FALL", x, y, mask=M("sprFallingBlock"), xs=xs, ys=ys,
            flags=XEF_KILLER, p=[40, 0, 6.25, 0, 4, 1, 0], inst=inst)
        return True
    if obj == "FallStair":
        tag = add("XB_SHAKE_FALL", x, y, mask=M("sprCastlevaniaFloorTrap"),
                  xs=xs, ys=ys, p=[20, 0, 6.25, 0, 2, 0, 1], inst=inst)
        solid = add("XB_TETBLOCK", x, y,
                    mask=M("sprCastlevaniaFloorTrap"), xs=xs, ys=ys,
                    flags=XEF_SOLID, note="FallStair.hitbox")
        ctx.deferred.append(("link", tag, solid))
        return True
    if obj == "RevealingSpikesUp":
        add("XB_REVEALING", x, y, mask=M("sprSpikeUp"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "SpikeUpExtend":
        tag = add("XB_SPIKE_EXTEND", x, y, mask=M("sprSpikeStretch"),
                  xs=xs, ys=ys, flags=XEF_KILLER, inst=inst)
        shaft = add("XB_KILLER", x, y + 32,
                    mask=build.masks.rect_mask(32, 32),
                    flags=XEF_KILLER, note="SpikeUpExtend.blockKill")
        ctx.xents[shaft]["ys"] = 0.0
        ctx.deferred.append(("link", tag, shaft))
        return True
    if obj == "SpikeTrap":
        tag = add("XB_SPIKETRAP", x, y,
                  mask=build.masks.rect_mask(64, 16, 0, -1),
                  flags=XEF_PLATFORM, inst=inst)
        face = add("XB_KILLER", x, y + 8,
                   mask=build.masks.rect_mask(64, 16),
                   flags=XEF_KILLER, note="SpikeTrap.blockKill")
        ctx.deferred.append(("link", tag, face))
        return True
    if obj == "QuickLaser":
        add("XB_QUICKLASER", x, y, mask=M("sprQuickLaser"), xs=1, ys=ys,
            flags=XEF_KILLER,
            p=[cc.get("c", 0), cc.get("length", 0), cc.get("delay", 0),
               cc.get("image_angle", 0.0)], inst=inst)
        return True
    if obj == "QuickLaserTimer":
        add("XB_QLTIMER", x, y, mask=M("maskTrigger"), xs=2, ys=ys,
            inst=inst)
        return True
    if obj == "PaintingTrap":
        add("XB_PAINTING", x, y, mask=M("sprPaintingTrap"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "WheelTrap":
        add("XB_WHEEL", x, y, mask=M("sprWheelTrap"), xs=xs, ys=ys,
            flags=XEF_KILLER | XEF_FORCE_ACTIVE, inst=inst)
        return True
    if obj == "FlyingSpike":
        add("XB_FLYSPIKE", x, y, mask=M("sprFlyingSpike"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "couchTrap":
        add("XB_COUCH", x, y, mask=M("sprCouchTrap"), xs=xs, ys=ys,
            inst=inst)
        return True
    if obj == "Hammer":
        add("XB_HAMMER", x, y, mask=M("sprHammer"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "HammerTrigger":
        tag = add("XB_TRIGGER", x, y, mask=M("sprHammerTrigger"),
                  xs=xs, ys=ys, p=[-1, -1, -1, TGT_NONE, 0, 0, 0],
                  inst=inst)
        ctx.deferred.append(("hammer_trigger", tag, inst))
        return True
    if obj == "TheSpikeYouShoot":
        add("XB_SPIKESHOOT", x, y, mask=M("sprSpikeRight"), xs=xs, ys=ys,
            flags=XEF_KILLER | XEF_SHOOTABLE, inst=inst)
        return True
    if obj == "FirstRoomSpike":
        add("XB_FRSPIKE", x, y, mask=M("sprGuySpikeTrap"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "FirstRoomBarrier":
        add("XB_FRBARRIER", x, y, mask=M("sprGuySpikeTrapBarrier"),
            xs=xs, ys=ys, flags=XEF_SOLID, inst=inst)
        return True
    if obj == "Higger":
        add("XB_HIGGER", x, y, mask=M("maskTrigger"), xs=7, ys=ys,
            inst=inst)
        return True
    if obj == "KillPill":
        add("XB_KILLPILL", x, y, mask=M("sprKillPill"), xs=18, ys=18,
            flags=XEF_KILLER | XEF_FORCE_ACTIVE, inst=inst)
        return True

    # ---- enemies ---------------------------------------------------------
    if obj == "MedusaHead":
        add("XB_MEDUSA", x, y, mask=M("sprMedusa"), xs=xs, ys=ys,
            flags=XEF_SHOOTABLE, p=[3.75], inst=inst)
        return True
    if obj == "MedusaMaker":
        pts = _load_path(build.source_root, "pMedusaMaker")
        trace = sample_path(pts["points"], pts["smooth"], pts["closed"],
                            speed=12.5, max_frames=4000, loops=1)
        flat = [c for xy in trace for c in xy]
        off, n = build.add_keys(flat)
        add("XB_MEDUSAMAKER", x, y, mask=M("sprControllerMMF2"),
            p=[cc.get("dir", 1.0), off, n // 2,
               build.template_for("MedusaHead")], inst=inst)
        return True
    if obj in ("Ghoul",):
        add("XB_GHOUL", x, y, mask=M("sprGhoul"), xs=xs, ys=ys,
            flags=XEF_SHOOTABLE, inst=inst)
        return True
    if obj == "GhoulGenerator":
        add("XB_GHOULGEN", x, y, mask=M("sprControllerMMF2"),
            p=[build.template_for("Ghoul")], inst=inst)
        return True
    if obj == "HoverGunner":
        add("XB_HOVERGUNNER", x, y, mask=M("sprTurret"), xs=xs, ys=ys,
            flags=XEF_SHOOTABLE,
            p=[0, build.template_for("HoverShot")], inst=inst)
        return True
    if obj == "SniperJohn":
        add("XB_SNIPER", x, y, mask=M("sprSniper"), xs=xs, ys=ys,
            flags=XEF_SHOOTABLE,
            p=[0, build.template_for("HoverShot")], inst=inst)
        return True
    if obj == "TourianTurret":
        add("XB_TOURTURRET", x, y, mask=M("sprMetroidTurret"), xs=xs, ys=ys,
            p=[0, build.template_for("TourianTurretBullet")], inst=inst)
        return True
    if obj == "Skwee":
        add("XB_SKWEE", x, y, mask=M("sprSkree"), xs=xs, ys=ys,
            flags=XEF_KILLER | XEF_SHOOTABLE, inst=inst)
        return True
    if obj == "SkweeTrigger":
        tag = add("XB_TRIGGER", x, y, mask=M("maskTrigger"),
                  xs=149 / 32.0, ys=479 / 32.0,
                  p=[-1, -1, -1, TGT_NONE, 0, 0, 0], inst=inst)
        ctx.deferred.append(("skwee_trigger", tag, inst))
        return True
    if obj == "Crawler":
        add("XB_CRAWLER", x, y, mask=M("sprCrawler"), xs=xs, ys=ys,
            flags=XEF_KILLER | XEF_SHOOTABLE,
            p=[0, 0, 0, 0, 0, 0, 0, 0, 270], inst=inst)
        return True
    if obj == "metroidTrap":
        add("XB_METROIDTRAP", x, y, mask=M("maskTrigger"),
            xs=156 / 32.0, ys=187 / 32.0,
            p=[build.template_for("Metroid")], inst=inst)
        return True
    if obj == "SpaghettiosDispenser":
        add("XB_SPAGDISP", x, y, mask=M("sprSpaghettios"), xs=xs, ys=ys,
            p=[build.template_for("Spaghettio")], inst=inst)
        return True
    if obj == "WatchFor":
        add("XB_WATCHFOR", x, y, mask=M("sprControllerMMF2"),
            p=[build.template_for("RollingRocks")], inst=inst)
        return True
    if obj == "Kamek":
        add("XB_KAMEK", x, y, mask=M("sprKamek"), xs=2, ys=2,
            p=[build.template_for("Playstation")], inst=inst)
        return True
    if obj == "Eggplant":
        add("XB_EGGPLANT", x, y, mask=M("sprEggplant"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "BouncyFruit":
        add("XB_BOUNCYFRUIT", x, y, mask=M("sprCherry"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "Witch":
        add("XB_WITCH", x, y, mask=M("sprWitch"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "WitchShadow":
        pts = _load_path(build.source_root, "pWitchShadow")
        trace = sample_path(pts["points"], pts["smooth"], pts["closed"],
                            speed=12.5, max_frames=2000, loops=1)
        flat = [c for xy in trace for c in xy]
        off, n = build.add_keys(flat)
        add("XB_WITCHSHADOW", x, y, mask=M("sprWitchShadow"),
            p=[0, off, n // 2], inst=inst)
        return True
    if obj == "Lonk":
        tag = add("XB_LONK", x, y, mask=M("sprLonk1"), xs=5, ys=5,
                  inst=inst)
        plat = add("XB_MARKER", x - 37, y,
                   mask=build.masks.rect_mask(75, 64),
                   flags=XEF_PLATFORM, p=[XM_GENERIC],
                   note="Lonk.platform")
        ctx.deferred.append(("link", tag, plat))
        return True
    if obj == "RoadCheep":
        add("XB_CHEEP", x, y, mask=M("sprRoadCheep"), xs=2, ys=2,
            flags=XEF_SHOOTABLE, inst=inst)
        return True
    if obj == "CheepController":
        add("XB_CHEEPCTL", x, y, mask=M("sprControllerMMF2"), inst=inst)
        return True
    if obj == "RoadBulletBill":
        add("XB_BULLETBILL", x, y, mask=M("sprBulletBill"), xs=-1, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    return _emit_class2(build, ctx, ir_room, inst, obj, x, y, xs, ys, cc,
                        roomvars, triggers)


def _emit_class2(build, ctx, ir_room, inst, obj, x, y, xs, ys, cc, roomvars,
                 triggers):
    M = build.mask
    add = ctx.add

    # ---- platforms & vehicles -------------------------------------------
    if obj in ("movingPlatform", "LongForm"):
        spr = "sprLongPlatform" if obj == "LongForm" else "sprDynamicPlatform01"
        flags = XEF_PLATFORM
        if cc.get("nopush"):
            flags |= XEF_NOPUSH
        if cc.get("stopper"):
            flags |= XEF_STOPPER
        if obj == "LongForm" and ctx.rname == "rGuyTower":
            flags |= XEF_NOBOUNCE
        vx = cc.get("hspeed", 2.0 if obj == "LongForm" else 0.0)
        vy = cc.get("vspeed", 0.0)
        add("XB_MOVPLAT", x, y, mask=M(spr), xs=xs, ys=ys, flags=flags,
            p=[vx, vy], inst=inst)
        return True
    if obj == "platform":
        add("XB_MARKER", x, y, mask=M("sprDynamicPlatform01"),
            xs=xs, ys=ys, flags=XEF_PLATFORM, p=[XM_GENERIC], inst=inst)
        return True
    if obj in ("FallingBrick", "FallingFort", "FactoryPlatform",
               "OutskirtPlatform"):
        spr = {"FallingBrick": "sprGuyFallingBrick",
               "FallingFort": "sprFallBlockFort",
               "FactoryPlatform": "sprBlockWana",
               "OutskirtPlatform": "sprArkaBrickSmall"}[obj]
        up = -1.0 if cc.get("up") else 1.0
        p = {"FallingBrick":   [4, 3, 1, 0, 0, 0],
             "FallingFort":    [0, 2, 1, 1, 1, 0],
             "FactoryPlatform": [0, 2, up, 0, 0, 1],
             "OutskirtPlatform": [0, 2, up, 0, 1, 0]}[obj]
        tag = add("XB_FALLPLAT", x, y, mask=M(spr), xs=xs, ys=ys,
                  flags=XEF_PLATFORM | XEF_NOBOUNCE, p=p, inst=inst)
        if obj == "FallingFort":
            solid = add("XB_TETBLOCK", x, y + 2,
                        mask=build.masks.rect_mask(32, 30),
                        flags=XEF_SOLID, note="FallingFort.blockNotMerge")
            ctx.deferred.append(("link", tag, solid))
        return True
    if obj == "metroidPlatform":
        add("XB_METROIDPLAT", x, y, mask=M("sprMetroidPlatform"),
            xs=xs, ys=ys, flags=XEF_PLATFORM | XEF_NOBOUNCE, inst=inst)
        return True
    if obj == "AscentPlatform":
        add("XB_ASCENT", x, y, mask=M("sprAscentPlatform"), xs=xs, ys=ys,
            flags=XEF_PLATFORM | XEF_NOBOUNCE, inst=inst)
        return True
    if obj == "AscentSpeedMod":
        add("XB_ASCENTMOD", x, y, mask=M("sprControllerMMF2"),
            xs=2, ys=13 / 32.0, inst=inst)
        return True
    if obj == "KumoPlatform":
        add("XB_KUMO", x, y, mask=build.masks.rect_mask(96, 16, -7, -7),
            flags=XEF_PLATFORM | XEF_NOBOUNCE, inst=inst)
        return True
    if obj == "GuyPlatform":
        vy = -1.0 if x == 1952 else 3.0
        add("XB_GUYPLAT", x, y, mask=build.masks.rect_mask(92, 16),
            flags=XEF_PLATFORM | XEF_NOBOUNCE, p=[vy], inst=inst)
        return True
    if obj == "PillarMove":
        tag = add("XB_PILLAR", x, y, mask=M("sprPillarMove"), inst=inst)
        plat = add("XB_MARKER", x + 96, y,
                   mask=M("sprDynamicPlatform01"),
                   flags=XEF_PLATFORM, p=[XM_GENERIC],
                   note="PillarMove.platform")
        ctx.deferred.append(("link", tag, plat))
        return True
    if obj == "HillMove":
        add("XB_HILL", x, y, mask=M("sprHillMove"), xs=xs, ys=ys,
            flags=XEF_SOLID, inst=inst)
        return True
    if obj == "Cart":
        wall = add("XB_TETBLOCK", 22368, 0,
                   mask=build.masks.rect_mask(32, 608),
                   flags=XEF_SOLID | XEF_START_INACTIVE,
                   note="Cart.crash_wall")
        add("XB_CART", x, y, mask=M("sprCart"),
            flags=XEF_FORCE_ACTIVE,
            p=[0, 0, 0, 0, 0, 0, 0, wall], inst=inst)
        return True
    if obj == "CartSpeedup":
        add("XB_CARTPICKUP", x, y, mask=M("sprControllerMMF2"), inst=inst)
        return True
    if obj == "BiggusBrickus":
        for dy in range(-128, 32, 32):
            for dx in (0, 32):
                add("XB_DESTRUCTIBLE", x + dx, y - 32 + dy + 32,
                    mask=build.masks.rect_mask(32, 32),
                    flags=XEF_SOLID, inst=inst,
                    note="BiggusBrickus.column")
        return True
    if obj == "blockTrapDestructible":
        add("XB_DESTRUCTIBLE", x, y, mask=build.masks.rect_mask(32, 32),
            xs=1, ys=1, flags=XEF_SOLID, inst=inst)
        return True
    if obj == "TysonBrick":
        # blockTrapDestructible child (1.25-tall solid); only boss events
        # break these -> permanent solids in non-boss play
        add("XB_DESTRUCTIBLE", x, y, mask=build.masks.rect_mask(32, 40),
            flags=XEF_SOLID, inst=inst)
        return True
    # (TysonDoor became a removable solid xent in the boss milestone;
    # bosses.emit_class handles it)

    # ---- yoku chains / tetris -------------------------------------------
    if obj == "FactoryYokuController":
        chain = []
        seen_base = False
        for other in ctx.src.instances:
            if other.object == "FactoryYoku":
                if other.id_hex == "002D80B8":
                    seen_base = True
                if seen_base:
                    chain.append(other.id_hex)
            elif seen_base and chain:
                break
        ctx.deferred.append(("factory_chain", inst, chain))
        add("XB_FACTORYCTL", x, y, mask=M("sprFactoryYokuController"),
            p=[0, 0, 0, 0, 0, 0, 0, 0, 0], inst=inst)
        return True
    if obj == "FactoryYoku":
        frame0 = 0.0 if inst.id_hex == "002D80B8" else 6.0
        add("XB_FACTORYBLOCK", x, y, mask=M("sprFactoryYoku"),
            flags=XEF_PLATFORM, p=[frame0], inst=inst)
        return True
    if obj == "RealYoku":
        add("XB_REALYOKU", x, y, mask=M("sprRealYoku"),
            flags=XEF_PLATFORM, p=[cc.get("my_id", 0.0)], inst=inst)
        return True
    if obj == "RealYokuController":
        add("XB_REALYOKUCTL", x, y, mask=M("sprControllerMMF2"), inst=inst)
        return True
    if obj == "RealYokuEndTrigger":
        tag = add("XB_TRIGGER", x, y, mask=M("maskTrigger"), xs=xs, ys=ys,
                  p=[-1, -1, -1, TGT_NONE, 0, 0, 0], inst=inst)
        ctx.deferred.append(("realyoku_end", tag, inst))
        return True
    if obj == "tetrisController":
        ev = build.proj.objects["tetrisController"].event("Create_0")
        n_slots, events = simulate_tetris(ev.code)
        slot0 = len(ctx.xents)
        for k in range(n_slots):
            add("XB_TETBLOCK", -1000, -1000,
                mask=build.masks.rect_mask(32, 32),
                flags=XEF_SOLID | XEF_START_INACTIVE,
                note=f"tetris.slot{k}")
        timeline = []
        for evt in events:
            t = evt[0] + 15          # timer starts at -15
            if evt[1] == "show":
                _, _, sid, ex, ey = evt
                timeline += [t, 2, slot0 + sid, ex]
                timeline += [t, 3, slot0 + sid, ey]
                timeline += [t, 0, slot0 + sid, 0]
            elif evt[1] == "hide":
                timeline += [t, 1, slot0 + evt[2], 0]
            elif evt[1] == "move":
                _, _, sid, ex, ey = evt
                timeline += [t, 2, slot0 + sid, ex]
                timeline += [t, 3, slot0 + sid, ey]
            elif evt[1] == "pill":
                timeline += [t, 4, build.template_for("KillPill"), 0]
        off, n = build.add_keys(timeline)
        add("XB_TETRIS", x, y, mask=M("sprControllerMMF2"),
            p=[0, off, n // 4, build.template_for("block")], inst=inst)
        return True

    # ---- interactive / pickups ------------------------------------------
    if obj in ("RyuButton", "PlatformReset"):
        kind = 1.0 if obj == "RyuButton" else 0.0
        add("XB_BUTTON", x, y, mask=M("sprButtonShoot"), xs=xs, ys=ys,
            flags=XEF_SHOOTABLE,
            p=[kind, 0, 0, 0, 0, 0, 0, 0, 1.0 if kind else 0.0], inst=inst)
        return True
    if obj == "ShootyBarrier":
        add("XB_SHOOTBARRIER", x, y, mask=M("sprMetroidShootyBarriers"),
            xs=xs, ys=ys, flags=XEF_SOLID | XEF_SHOOTABLE, inst=inst)
        return True
    if obj == "NatsCat":
        add("XB_NATSCAT", x, y, mask=M("sprCuteKitty"), xs=xs, ys=ys,
            flags=XEF_SOLID | XEF_SHOOTABLE,
            p=[build.template_for("CUTE_KITTY_BOOM")], inst=inst)
        return True
    if obj == "ChozoOrb":
        add("XB_CHOZO", x, y, mask=M("sprChozoOrb"), xs=xs, ys=ys,
            flags=XEF_KILLER | XEF_SHOOTABLE,
            p=[build.template_for("secret4")], inst=inst)
        return True
    if obj == "deliciousFruit":
        add("XB_FRUIT", x, y, mask=M("sprCherry"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "CatThing":
        add("XB_CATTHING", x, y, mask=M("sprCatThing"), xs=xs, ys=ys,
            p=[build.template_for("deliciousFruit")], inst=inst)
        return True
    if obj == "FireChalice":
        add("XB_FIRECHALICE", x, y, mask=M("sprFireChalice"), xs=xs, ys=ys,
            flags=XEF_KILLER, inst=inst)
        return True
    if obj == "Ryu":
        pts = _load_path(build.source_root, "pRyu")
        trace = sample_path(pts["points"], pts["smooth"], pts["closed"],
                            speed=11.25, max_frames=2000, loops=1)
        flat = [c for xy in trace for c in xy]
        off, n = build.add_keys(flat)
        add("XB_RYU", x, y, mask=M("sprTatsumaki"), xs=2, ys=2,
            flags=XEF_KILLER, p=[0, off, n // 2], inst=inst)
        return True
    if obj == "RyuWind":
        add("XB_RYUWIND", x, y, mask=M("sprBlockNise"), xs=xs, ys=ys,
            inst=inst)
        return True
    if obj == "MoonSmall":
        # rMechaBirdoBoss instance falls from creation (cc vspeed=6)
        add("XB_MOONSMALL", x, y, mask=M("sprMoonSmall"), xs=xs, ys=ys,
            p=[cc.get("vspeed", 0.0)], inst=inst)
        return True
    if obj in ("OrbBirdo", "OrbMother"):
        flag = PROGRESSION_FLAGS["orb_birdo" if obj == "OrbBirdo"
                                 else "orb_mother"]
        add("XB_ORB", x, y, mask=M("sprUnit"), xs=xs, ys=ys,
            p=[flag], inst=inst)
        return True
    if obj in ("secret1", "secret2", "secret3", "secret4", "secret5",
               "secret6"):
        add("XB_SECRET", x, y, mask=M(f"sprSecret{obj[-1]}"), xs=xs, ys=ys,
            p=[SECRET_FLAGS[obj]], inst=inst)
        return True
    if obj == "BlownEntrance":
        add("XB_CONDSOLID", x, y, mask=M("sprBlownEntrance"), xs=xs, ys=ys,
            flags=XEF_SOLID, p=[PROGRESSION_FLAGS["orb_mother"], 1, 0],
            inst=inst)
        return True
    if obj == "FactoryCeiling":
        add("XB_CONDSOLID", x, y, mask=M("sprFactoryCeiling"), xs=xs, ys=ys,
            flags=XEF_SOLID | XEF_KILLER, p=[0, 0, 77], inst=inst)
        return True
    if obj == "TourianBarrier":
        add("XB_TOURIANBARRIER", x, y, mask=M("sprGuySpikeTrapBarrier"),
            xs=xs, ys=ys, flags=XEF_SOLID,
            p=[PROGRESSION_FLAGS["orb_mother"]], inst=inst)
        return True
    if obj == "Torizo":
        _rasterize_solid(build, ctx, ir_room, inst, roomvars)
        build.coverage["static"][obj] += 1
        return "static"
    if obj in ("WalljumpL", "WalljumpR", "yellowallL", "yellowallR",
               "WeirdYellowWallL", "WeirdYellowWallR"):
        side = 0.0 if obj.endswith("L") else 1.0
        kind = XW_PLAIN
        if obj.startswith("yellowall"):
            kind = XW_YELLOW
        elif obj.startswith("Weird"):
            kind = XW_WEIRD
        spr = {"WalljumpL": "sprWallL", "WalljumpR": "sprWallR",
               "yellowallL": "sprYellowallL", "yellowallR": "sprYellowallR",
               "WeirdYellowWallL": "sprYellowallL",
               "WeirdYellowWallR": "sprYellowallR"}[obj]
        add("XB_WALLSTRIP", x, y, mask=M(spr), xs=xs, ys=ys,
            p=[side, kind], inst=inst)
        return True
    if obj == "objWater2":
        add("XB_WATER", x, y, mask=M("sprWater"), xs=xs, ys=ys,
            p=[2], inst=inst)
        return True
    if obj == "objWater":
        add("XB_WATER", x, y, mask=M("sprWater"), xs=xs, ys=ys,
            p=[1], inst=inst)
        return True
    if obj in ("FactorySpinner1", "FactorySpinner2"):
        var = 1.0 if obj.endswith("1") else 2.0
        add("XB_SPINNER", x, y, mask=M(f"sprFactorySpinner{int(var)}"),
            xs=xs, ys=ys, flags=XEF_SOLID, p=[var], inst=inst)
        return True
    if obj == "FunnySpikeMan":
        walk = M("sprFunnySpikeManWalkin")
        base = M("sprFunnySpikeMan")
        add("XB_SPIKEMAN", x, y, mask=base, xs=xs, ys=ys,
            flags=XEF_KILLER, p=[0, 0, 0, 0, 0, walk, base], inst=inst)
        return True
    if obj == "SnifitCannon":
        laser = add("XB_KILLER", x, y, mask=M("spr_1x2"),
                    xs=640, ys=16, flags=XEF_KILLER | XEF_START_INACTIVE,
                    p=[0, 0, 0, 0, 0, 0, 0, 0, 0, 315.0],
                    note="SnifitCannon.laser")
        tag = add("XB_SNIFITCANNON", x, y, mask=M("sprCannon"),
                  p=[build.template_for("SnifitBullet")], inst=inst)
        ctx.deferred.append(("link", tag, laser))
        return True
    if obj == "EntranceTele":
        _emit_entrance_tele_stub(build, ctx, inst)
        return True
    if obj == "BossTeleporter":
        _emit_boss_teleporter(build, ctx, ir_room, inst, cc)
        return True

    # boss-arena classes (c_src/boss/ milestone; bosses.py)
    from . import bosses as _b
    r = _b.emit_class(build, ctx, ir_room, inst, obj, x, y, xs, ys, cc,
                      roomvars)
    if r is not None:
        return r
    return None


_TRIG_FIELD = re.compile(r'^\s*(i)\s*=\s*(.+?)\s*$', re.M)
_TRIG_STR = re.compile(r'\b([otc])\s*=\s*"((?:[^"\\]|\\.)*)"', re.S)


def _emit_trigger(build, ctx, tc, inst, cc, roomvars):
    code = inst.creation_code or ""
    ent = ctx.xents[ctx.ent_by_hex(inst.id_hex)]
    # i= target (an expression, not a string)
    tgt = TGT_NONE
    mi = re.search(r"^\s*i\s*=\s*([^\n\"]+?)\s*$", code, re.M)
    if mi:
        expr = mi.group(1).strip()
        if expr in build.proj.objects and ctx.is_excluded_class(expr):
            build.coverage["boss_exception_notes"].setdefault(
                ctx.rname, []).append(
                f"trigger {inst.id_hex} targets excluded class {expr}")
            tgt = TGT_NONE
        elif expr == "id":
            tgt = TGT_NONE
        else:
            try:
                tgt = tc.resolve_target(expr, inst)
            except ConversionError:
                # reference to an instance imported as static geometry or
                # excluded content: cosmetic-only trigger target
                hex_id = expr.split("_")[-1]
                ref = next((i2 for i2 in ctx.src.instances
                            if i2.id_hex == hex_id), None)
                if ref is not None and (
                        ref.object in STATIC_CLASSES or
                        ref.object in EXTRA_SOLID_CLASSES or
                        ref.object in ("TysonDoor", "Torizo") or
                        ctx.is_excluded_class(ref.object)):
                    build.coverage["boss_exception_notes"].setdefault(
                        ctx.rname, []).append(
                        f"trigger {inst.id_hex}: target {ref.object} "
                        f"({hex_id}) is static/cosmetic")
                    tgt = TGT_NONE
                else:
                    raise
    progs = {"o": (-1, 0), "t": (-1, 0), "c": (-1, 0)}
    for m in _TRIG_STR.finditer(code):
        kind, text = m.group(1), m.group(2)
        ops = tc.compile_code(text, inst, tgt)
        # spd on Up-variant spikes: the stored p[2] is SIGNED
        if tgt <= TGT_CLS0 or tgt >= 0:
            tgt_obj = None
            if mi:
                tgt_obj = mi.group(1).strip()
            if tgt_obj == "FallingSpike10frameUp":
                ops = [(n, t2, -abs(a), b, c2) if n == "XOP_SET_P" and b > 0
                       else (n, t2, a, b, c2)
                       for (n, t2, a, b, c2) in ops]
                ops = [(n, t2, a, -abs(b), c2) if n == "XOP_SET_P" else
                       (n, t2, a, b, c2) for (n, t2, a, b, c2) in ops]
        progs[kind] = build.asm.emit(ops) if ops else (-1, 0)
    ent["p"][0] = float(progs["o"][0])
    ent["p"][5] = float(progs["o"][1])
    ent["p"][1] = float(progs["t"][0])
    ent["p"][4] = float(progs["t"][1])
    ent["p"][2] = float(progs["c"][0])
    ent["p"][6] = float(progs["c"][1])
    ent["p"][3] = float(tgt)


def _finish_deferred(build, ctx):
    """Second-pass links that needed the full entity table."""
    for item in list(ctx.deferred):
        kind = item[0]
        if kind == "hammer_trigger":
            _, tag, inst = item
            hammer = None
            for i, e in enumerate(ctx.xents):
                if e["cls"] == C["XB_HAMMER"]:
                    hammer = i
            ops = [("XOP_SET_VY", hammer, 6.25, 0, 0),
                   ("XOP_DESTROY", TGT_SELF, 0, 0, 0)]
            off, n = build.asm.emit(ops)
            ctx.xents[tag]["p"][1] = float(off)
            ctx.xents[tag]["p"][4] = float(n)
        elif kind == "skwee_trigger":
            _, tag, inst = item
            hits = ctx.overlapping_of_class(inst, "Skwee", all_hits=True)
            ops = [("XOP_SET_ACTIVE", h, 1, 0, 0) for h in hits]
            ops.append(("XOP_DESTROY", TGT_SELF, 0, 0, 0))
            off, n = build.asm.emit(ops)
            ctx.xents[tag]["p"][1] = float(off)
            ctx.xents[tag]["p"][4] = float(n)
        elif kind == "realyoku_end":
            _, tag, inst = item
            ops = [("XOP_SET_P", TGT_CLS0 - C["XB_REALYOKU"], 9, 1, 0),
                   ("XOP_EVENT", TGT_CLS0 - C["XB_REALYOKU"], 0, 0, 0),
                   ("XOP_DESTROY", TGT_CLS0 - C["XB_REALYOKUCTL"], 0, 0, 0),
                   ("XOP_DESTROY", TGT_SELF, 0, 0, 0)]
            off, n = build.asm.emit(ops)
            ctx.xents[tag]["p"][1] = float(off)
            ctx.xents[tag]["p"][4] = float(n)
        elif kind == "factory_chain":
            _, inst, chain_hex = item
            idxs = [ctx.ent_by_hex(h) for h in chain_hex]
            off, n = build.add_keys([float(i) for i in idxs])
            for e in ctx.xents:
                if e["cls"] == C["XB_FACTORYCTL"]:
                    e["p"][1] = float(off)
                    e["p"][2] = float(n)
            # chain members: link to the previous member (disappear cue)
            for k in range(1, len(idxs)):
                ctx.xents[idxs[k]]["link"] = idxs[k - 1]


def _emit_entrance_tele_stub(build, ctx, inst):
    """EntranceTele: 6-orb AND gate; kills without all orbs (source)."""
    flags6 = [PROGRESSION_FLAGS[k] for k in
              ("orb_tyson", "orb_mother", "orb_bowser", "orb_birdo",
               "orb_dracula", "orb_kraidgief")]
    road = build.room_index["rGuyRoad"]
    ctx.add("XB_ENTRANCETELE", inst.x, inst.y,
            mask=build.masks.rect_mask(370 * 2 // 2 * 0 + 16, 32) if False
            else build.mask("sprBlockMini"),
            xs=370 / 16.0, ys=inst.yscale,
            p=flags6 + [road], inst=inst)


def _emit_boss_teleporter(build, ctx, ir_room, inst, cc):
    """BossTeleporter (par=warp override): active only once the matching
    orb flag is set; then a plain position warp (objects/BossTeleporter.gml).
    Lowered through the v2 conditional-warp machinery (dormant warp +
    flag_set activation event)."""
    ttype = str(cc.get("type", "")).strip('"')
    table = {
        "tyson":     ("orb_tyson", "rGuy1", 4000, 304),
        "birdo":     ("orb_birdo", "rFactoryOutskirts", 32, 976),
        "kraidgief": ("orb_kraidgief", "rMegaman", 32, 400),
        "dracula":   ("orb_dracula", "rFactoryOutskirts", 2464, 1072),
        "mother":    ("orb_mother", "rFactoryOutskirts", 928, 3600),
        "bowser":    ("orb_bowser", "rBowserBoss", 832, 496),
        "dragon":    ("orb_dragon", "rGuyRoad", 23392, 496),
        "guy":       ("orb_guy", "rGuyTower", 736, 416),
    }
    if ttype == "dev":
        build.coverage["excluded_visual"]["BossTeleporter.dev"] += 1
        return
    if ttype not in table:
        raise ConversionError(f"BossTeleporter type {ttype!r}")
    flagname, dest, wx, wy = table[ttype]
    tag = 60 + len([w for w in ir_room["warps"] if w.get("tag", 0) >= 60])
    ir_room["warps"].append({
        "x": inst.x + 16.0, "y": inst.y + 16.0,
        "half_w": 16.0, "half_h": 16.0,
        "mode": "absolute",
        "dest_x": float(wx), "dest_y": float(wy),
        "dest_room": build.room_index[dest],
        "tag": tag, "active": False,
        "source_instance": inst.id_hex})
    ir_room["events"].append({
        "when": "flag_set", "flag": PROGRESSION_FLAGS[flagname],
        "once": True,
        "actions": [{"do": "activate", "tag": tag}],
        "mapping_status": "exact",
        "provenance": {"source_room": ctx.rname,
                       "source_instance": inst.id_hex,
                       "source_event": f"BossTeleporter[{ttype}]"}})


# ---------------------------------------------------------------------------
# Top-level build + serialization into the IR
# ---------------------------------------------------------------------------

def build_exact(source_root: str, proj, result: dict) -> dict:
    """Augment the static-conversion result with the exact-behavior layer.
    Mutates result["ir"] (adds ir["exact"], extends room solids/warps/events)
    and returns the exact coverage report."""
    ir = result["ir"]
    room_names = [r["name"] for r in ir["rooms"]]
    room_index = {n: i for i, n in enumerate(room_names)}
    build = ExactBuild(source_root, proj, ir, room_index)

    ir_rooms = {r["name"]: r for r in ir["rooms"]}
    from . import bosses
    xrooms = []
    for rname in room_names:
        if rname in GAMEPLAY_ROOMS or rname in bosses.BOSS_ROOMS:
            xr = emit_room(build, rname, ir_rooms[rname])
        else:
            xr = {"name": rname, "xents": [], "camera": XCAM_NONE,
                  "always_active": 0, "enter_ops": [0, 0], "kind": 0}
        xrooms.append(xr)

    # warp side-effect ops (code= strings recorded by the static pass)
    for eff in result["coverage"].get("side_effects", []):
        rname = eff["room"]
        if rname not in GAMEPLAY_ROOMS:
            continue
        code = eff["code"]
        ctx = RoomCtx(build, rname)      # target resolution not needed here
        tc = TriggerCompiler(ctx)
        class _FakeInst:
            id_hex = "warpcode"
            object = "warp"
        ops = tc.compile_code(code, _FakeInst(), TGT_NONE)
        if not ops:
            eff["status"] = "no-op after compilation"
            continue
        off, n = build.asm.emit(ops)
        # attach to the matching warp record (same position)
        room = ir_rooms[rname]
        best = None
        for w in room.get("warps", []):
            if abs(w["x"] - eff["at"][0]) < 64 + abs(w.get("half_w", 0)) and \
                    abs(w["y"] - eff["at"][1]) < 640:
                best = w
        for w in room.get("warps", []):
            pass
        # precise match: the static converter stored warp center; match on
        # source instance position via provenance when available
        cands = [w for w in room.get("warps", [])
                 if w.get("source_instance") and
                 _warp_matches(proj, rname, w, eff["at"])]
        if cands:
            best = cands[0]
        if best is None:
            raise ConversionError(
                f"warp side effect at {eff['at']} in {rname} matches no warp")
        best["xop0"] = off
        best["xnops"] = n
        eff["status"] = "compiled"

    build.xrooms = xrooms
    ir["exact"] = {
        "hb": [-5, -12, 5, 8],          # sprMask: 11x21 (mechanics doc)
        "flags": 1 | 2,                  # exact physics + smoothmetroid dflt
        "masks": [_mask_json(m) for m in build.masks.masks],
        "ops": build.asm.ops,
        "keys": build.keys,
        "templates": build.templates,
        "rooms": xrooms,
    }
    cov = build.coverage
    cov["implemented"] = dict(cov["implemented"])
    cov["static"] = dict(cov["static"])
    cov["implemented_boss"] = dict(cov["implemented_boss"])
    cov["excluded_visual"] = dict(cov["excluded_visual"])
    cov["excluded_boss"] = dict(cov["excluded_boss"])
    return cov


def _warp_matches(proj, rname, w, at):
    inst = next((i for i in proj.rooms[rname].instances
                 if i.id_hex == w.get("source_instance")), None)
    return inst is not None and abs(inst.x - at[0]) < 1 and \
        abs(inst.y - at[1]) < 1


def _mask_json(m):
    out = {k: m[k] for k in ("sprite", "ox", "oy", "bl", "bt", "br", "bb",
                             "shape", "w", "h")}
    out["nframes"] = max(1, len(m["frames"]))
    out["rows"] = [[format(r, "x") for r in fr] for fr in m["frames"]]
    return out
