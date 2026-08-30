"""Scripted reference drivers for IWBTGR 1.5.3 full-game progression.

Each ``drive_*`` function plays one gameplay segment on a live
:class:`~iwanna_gym.clib.CIWanna` env whose current room contains the
segment, pinning the player with ``set_state`` (tool-assisted piloting:
the driver chooses positions, the engine simulates everything else —
boss logic, projectiles, damage, flags, transitions).  All drivers are
deterministic for a fixed seed; the canonical seed is 11.

``run_full_game`` chains every segment into a single-session run from
the game's start room (rGuy1) to the completion event in rEnding:
all eight source bosses, all six orb flags, the EntranceTele gate, the
final-area chain, and the ending — with zero deaths.

These drivers double as the reproducible reference suite required by
the exact-game milestone: ``tests/test_iwbtgr_fullgame.py`` executes
them, and ``scripts/record_reference_traces.py`` hashes their
trajectories.
"""
from __future__ import annotations

import math

from . import room_names

# exact-layer class ids (mirrors c_src/exact.h)
XC_ORB, XC_WEAK = 80, 96
XC_TYSON_DOOR = 114
XC_DEADCULA, XC_PLASM = 117, 123
XC_CC_BOMB, XC_CC_EXPL, XC_CC_BANZAI = 126, 127, 129
XC_MOMMY = 137
XC_DRAGON, XC_DFIRE = 139, 140
XC_MOON = 143
XC_SINISTAR, XC_VIPER, XC_GBOSS = 144, 145, 147
XC_BUGZ, XC_DRONE, XC_DBUL, XC_FRUIT = 148, 149, 150, 151
XC_ARKABALL, XC_ARKABRICK = 152, 154
XC_GF, XC_GH, XC_GEYE, XC_THEGUN = 155, 159, 160, 166

FLAG_TYSON, FLAG_BIRDO, FLAG_KRAIDGIEF = 0x2, 0x4, 0x8
FLAG_BOWSER, FLAG_MOTHER, FLAG_DRACULA = 0x10, 0x20, 0x40
FLAG_DRAGON, FLAG_GUY = 0x80, 0x100

# the searched VicViper flight plan (chunk targets, 50 frames each;
# "boss" = track the GradiusBoss's y to land shots)
VIPER_PLAN = [160, 160, 250, 350, 160, 350, 505, 160, 250, 160, 250,
              160, 160, 160, "boss", "boss"]


def _alive(c, cls):
    return [r for r in c.xents() if int(r[0]) == cls and r[6] > 0]


def _slot(c, defid):
    for r in c.bosses():
        if int(r[0]) == defid:
            return r
    return None


def _no_death(c, d0, where):
    if c.deaths != d0:
        raise AssertionError(f"unexpected death during {where}")


def goto(c, x, y, expect_room=None, max_t=40, act=2):
    """Pin-jump the player onto (x, y) — usually a warp rect — and step
    until the room changes (or ``max_t`` frames pass)."""
    room0 = c.room
    for _ in range(max_t):
        c.set_state(x, y, 0, 0, 1)
        c.step(act)
        if c.room != room0:
            break
    if expect_room is not None:
        names = room_names()
        got = names[c.room]
        if got != expect_room:
            raise AssertionError(f"goto({x},{y}): in {got}, "
                                 f"wanted {expect_room}")


def take_orb(c, ox=None, oy=None, max_t=60):
    """Touch the (only) orb in the room; returns once it is consumed or
    enters its delayed-warp countdown."""
    for _ in range(max_t):
        orbs = _alive(c, XC_ORB)
        if not orbs or int(orbs[0][5]) != 0:
            return True
        x = float(orbs[0][1]) if ox is None else ox
        y = float(orbs[0][2]) if oy is None else oy
        c.set_state(x, y, 0, 0, 1)
        c.step(2)
    return False


# --------------------------------------------------------------- Tyson

def drive_tyson(c, max_t=14000):
    """Mike Tyson (in rGuy1).  Park at the arena, wait out the door
    intro, shoot the weak box in the vulnerability windows, take the
    orb.  Ends still in rGuy1 with orb_tyson set."""
    d0 = c.deaths
    c.set_state(3210, 290, 0, 0, 1)
    for _ in range(4):
        c.step(2)
    for t in range(3000):                     # door intro / walk-in
        if len(c.bosses()):
            break
        c.step(2)
        _no_death(c, d0, "tyson intro")
    for t in range(max_t):
        b = c.bosses()
        if not len(b):
            break                             # slot released: he is dead
        if int(b[0][6]) & 1:                  # F_VULN
            wb = [w for w in _alive(c, XC_WEAK) if w[2] > -500]
            if wb:
                fx, fy = float(wb[0][1]), float(wb[0][2])
                c.set_state(fx - 90, fy - 4, 0, 0, 1)
                c.step(10 if t % 2 == 0 else 4)
                _no_death(c, d0, "tyson")
                continue
        c.set_state(3600, 407, 0, 0, 1)
        c.step(2)
        _no_death(c, d0, "tyson")
    assert take_orb(c), "tyson orb not found"
    _no_death(c, d0, "tyson orb")
    assert c.gflags & FLAG_TYSON


# --------------------------------------------------------------- Birdo

def drive_birdo(c, max_t=5000):
    """MechaBirdo (rMechaBirdoBoss).  Shoot the phase weak point from
    the left; his death code warps the run to rFactoryOutskirts."""
    names = room_names()
    room = names.index("rMechaBirdoBoss")
    d0 = c.deaths
    for t in range(max_t):
        if c.room != room:
            break
        b = c.bosses()
        a = 2
        if len(b):
            bx, by = float(b[0][10]), float(b[0][11])
            ph = int(b[0][1])
            if int(b[0][6]) & 2:              # F_DEAD
                c.set_state(400, 300, 0, 0, 1)
            else:
                wy = {1: by - 700.0, 2: by - 600.0, 3: by - 570.0}[ph]
                c.set_state(bx - 300, wy, 0, 0, 1)
                a = 8 if t % 2 == 0 else 2
        else:
            c.set_state(400, 300, 0, 0, 1)
        c.step(a)
        _no_death(c, d0, "birdo")
    assert names[c.room] == "rFactoryOutskirts", "birdo exit warp missing"
    # the OrbBirdo pickup sits along the exit path at (736,928)
    for _ in range(6):
        c.set_state(736, 932, 0, 0, 1)
        c.step(2)
        if c.gflags & FLAG_BIRDO:
            break
    _no_death(c, d0, "birdo orb")
    assert c.gflags & FLAG_BIRDO


# ----------------------------------------------------------- Kraidgief

def drive_kraidgief(c, max_t=110000):
    """Kraidgief (rKraidgiefBoss).  Fight the phases from the safe side,
    then walk the corpse hall right into the rMegaman exit warp."""
    names = room_names()
    room = names.index("rKraidgiefBoss")
    d0 = c.deaths
    saw_p4 = False
    for t in range(max_t):
        if c.room != room:
            break
        b = c.bosses()
        a = 2
        if len(b):
            f = int(b[0][6])
            ph = int(b[0][1])
            timer = int(b[0][2])
            spr = int(b[0][7])
            intro = f & 4
            if ph == 4:
                saw_p4 = True
            wps = _alive(c, XC_WEAK)
            proj = bool(_alive(c, 105))       # XB_KGPROJ
            fire = bool(_alive(c, 106))       # XB_KGFIRE
            wx, wy = ((float(wps[0][1]), float(wps[0][2])) if wps
                      else (-999, 0))
            if intro:
                c.set_state(400, 165, 0, 0, 1)
            elif ph in (0, 1):
                if proj or wx < -300:
                    c.set_state(10 if ph == 1 else 400,
                                100 if ph == 1 else 165, 0, 0, 1)
                else:
                    c.set_state(wx - 250, wy, 0, 0, 1)
                    a = 10 if t % 8 == 0 else 4
            elif ph == 2:
                if (spr != 6 or fire or wx < -300 or
                        900690 <= timer <= 900790):
                    c.set_state(1200, 150, 0, 0, 1)
                else:
                    c.set_state(wx - 250, wy - 48, 0, 0, 1)
                    a = 10 if t % 8 == 0 else 4
            elif ph == 4:
                c.set_state(1400, 300, 0, 0, 1)
        elif saw_p4:
            if c.x < 1500:
                c.set_state(min(1500, c.x + 6), 700, 0, 0, 1)
            else:
                c.set_state(c.x + 3, 780, 0, 0, 1)
        c.step(a)
        _no_death(c, d0, "kraidgief")
    assert names[c.room] == "rMegaman", "kraidgief exit warp missing"
    assert c.gflags & FLAG_KRAIDGIEF


# ------------------------------------------------------------- Dracula

def drive_dracula(c, max_t=30000):
    """Dracula -> Deadcula -> true form (rDraculaBoss).  The orb's
    delayed Alarm_0 warp then lands the run in rFactoryOutskirts at
    (3040,960)."""
    names = room_names()
    room = names.index("rDraculaBoss")
    d0 = c.deaths
    for t in range(2005):                     # intro cutscene
        c.step(4 if t >= 1645 else 2)
        _no_death(c, d0, "dracula intro")
    stage = "drac"
    for t in range(max_t):
        if c.room != room:
            break
        if stage == "drac":
            b = c.bosses()
            if not len(b):
                stage = "deadcula"
                continue
            dx = float(b[0][10])
            plasms = _alive(c, XC_PLASM)
            if 0 < dx < 800:
                side = -1 if dx > 400 else 1
                px = dx + side * 130
                if plasms and any(abs(float(p[1]) - px) < 90
                                  for p in plasms):
                    px = dx - side * 130
                c.set_state(px, 322, 0, 0, 1)
                a = 10 if px < dx else 6
                c.step(a if t % 2 == 0 else (4 if px < dx else 0))
            else:
                c.set_state(400, 90, 0, 0, 1)
                c.step(2)
        elif stage == "deadcula":
            dc = _alive(c, XC_DEADCULA)
            if not dc:
                if _alive(c, XC_ORB):
                    assert take_orb(c)
                    stage = "warp"
                    continue
                c.set_state(400, 90, 0, 0, 1)
                c.step(2)
                continue
            ddx, ddy = float(dc[0][1]), float(dc[0][2])
            st = int(dc[0][5])
            if st >= 3:                       # shootable true form
                side = -1 if ddx > 400 else 1
                c.set_state(ddx + side * 140, ddy - 40, 0, 0, 1)
                c.step((10 if side < 0 else 6) if t % 2 == 0 else 2)
            else:
                c.set_state(400, 90, 0, 0, 1)
                c.step(2)
        else:                                 # waiting out the orb alarm
            c.step(2)
        _no_death(c, d0, "dracula")
    assert names[c.room] == "rFactoryOutskirts", "dracula orb warp missing"
    assert c.gflags & FLAG_DRACULA


# ------------------------------------------------------------ ClownCar

_CC_PARKS = [(60, 90), (400, 60), (740, 90), (60, 300), (740, 300),
             (120, 560), (680, 560)]


def _cc_far_park(cx, cy, avoid=()):
    best, bd = (400, 90), -1
    for p in _CC_PARKS:
        d = math.hypot(p[0] - cx, p[1] - cy)
        for ax, ay in avoid:
            d = min(d, math.hypot(p[0] - ax, p[1] - ay))
        if d > bd:
            bd, best = d, p
    return best


def drive_clowncar(c, max_t=120000):
    """Koopa Clown Car: Bowser bombs -> Wart banzai -> Wily capsule
    (rBowserBoss).  Ends in-room with orb_bowser set."""
    def clampx(v):
        return max(40, min(760, v))

    d0 = c.deaths
    bomb_age = 0
    flip = 0
    slotless = 0
    for t in range(max_t):
        b = c.bosses()
        if not len(b):
            if _alive(c, XC_ORB):
                assert take_orb(c)
                break
            slotless += 1
            c.step(2)
            _no_death(c, d0, "clowncar post")
            assert slotless < 700, "clowncar: no orb after slot release"
            continue
        slotless = 0
        ph, T = int(b[0][1]), int(b[0][2])
        cx, cy = float(b[0][10]), float(b[0][11])
        flip ^= 1
        bombs = _alive(c, XC_CC_BOMB)
        bz = _alive(c, XC_CC_BANZAI)
        expls = [(float(e[1]), float(e[2]))
                 for e in _alive(c, XC_CC_EXPL)]
        px, py = _cc_far_park(cx, cy, avoid=expls)
        act = 2
        if ph == 0 and T >= 1900:
            pass                              # dead car rising: stay far
        elif ph == 0 and bombs:
            bx, by = float(bombs[0][1]), float(bombs[0][2])
            bomb_age += 1
            engage_ok = ((340 <= cx <= 660) or T >= 942) and \
                not (bx < 190 and cx <= bx + 30) and \
                not (bx > 690 and cx > bx)
            if bomb_age >= 296 or bx > 770 or by > 560 or not engage_ok:
                px, py = _cc_far_park(cx, cy, avoid=[(bx, by)] + expls)
            else:
                bvy = float(bombs[0][4])
                lead = bvy * 9.0 if abs(bvy) < 3.0 else 0.0
                wx = clampx(bx + 150) if bx < 230 else clampx(bx - 150)
                wy = min(max(by - 2 + lead, 60), 524)
                if by > 495:
                    wy = 508                  # bullet line above the floor
                if wx < cx - 96 < bx and abs(wy - cy) < 120:
                    wy = min(wy, cy - 100)    # shoot over the car's head

                def hit(rl, rr, rt, rb):
                    return (wx + 11 > rl and wx - 12 < rr and
                            wy + 15 > rt and wy - 18 < rb)
                danger = (hit(cx - 48, cx + 48, cy - 180, cy - 84) or
                          hit(cx - 96, cx + 95, cy - 84, cy + 83))
                if not danger:
                    px, py = wx, wy
                    act = (6 if bx < 230 else 10) if flip else \
                          (0 if bx < 230 else 4)
                else:
                    px, py = _cc_far_park(cx, cy,
                                          avoid=[(bx, by)] + expls)
        elif ph == 0:
            bomb_age = 0
            if T > 660 and abs(cx - 680) < 60 and cy < 260 and T < 1900:
                px, py, act = 562, 117, (10 if flip else 4)
        elif ph == 1 and bz:
            zx, zy = float(bz[0][1]), float(bz[0][2])
            px, py = clampx(zx - 105), zy + 30
            act = 10 if flip else 4
        elif ph == 2 and 6100 <= T < 10000:
            if cx >= 340:
                px, py = clampx(cx - 210), cy - 130
                act = 10 if flip else 4
            else:
                px, py = clampx(cx + 210), cy - 130
                act = 6 if flip else 0
        c.set_state(px, py, 0, 0, 1)
        c.step(act)
        _no_death(c, d0, "clowncar")
    assert c.gflags & FLAG_BOWSER


# ---------------------------------------------------------- Mother Brain

def drive_mommy(c, max_t=4000, leave=True):
    """Mother Brain (rMetroid).  Shoot through the glass window, ride
    out her death, grab the orb, and (leave=True) escape through the
    top warp to rFactoryOutskirts before the countdown detonates."""
    names = room_names()
    d0 = c.deaths
    m = _alive(c, XC_MOMMY)
    assert m, "mother brain not present"
    mx, my = float(m[0][1]), float(m[0][2])
    for t in range(max_t):
        mm = _alive(c, XC_MOMMY)
        if not mm:
            break
        if int(mm[0][5]) >= 2:                # dying / escape state
            c.set_state(400, 1340, 0, 0, 1)
            c.step(2)
        else:
            c.set_state(mx + 230, my + 55, 0, 0, 1)
            c.step(6 if t % 2 == 0 else 0)
        _no_death(c, d0, "mother brain")
    # cross the escape trigger on the chamber floor: she leaves and the
    # 3000-frame countdown starts (source room trigger -> event_user(0))
    for _ in range(10):
        mm = _alive(c, XC_MOMMY)
        if mm and int(mm[0][5]) == 4:
            break
        c.set_state(170, 1880, 0, 0, 1)
        c.step(2)
    mm = _alive(c, XC_MOMMY)
    assert mm and int(mm[0][5]) == 4, "escape countdown not armed"
    _no_death(c, d0, "escape trigger")
    assert take_orb(c, 2784, 224), "mother orb not reachable"
    _no_death(c, d0, "mother orb")
    assert c.gflags & FLAG_MOTHER
    if leave:
        goto(c, 2752, 64, "rFactoryOutskirts", max_t=80)
        _no_death(c, d0, "metroid escape")


# -------------------------------------------------------------- Dragon

_ROAD_HAZ = set(range(96, 170)) | {28, 34, 35, 66, 72}


def _road_best_y(c, px):
    hz = [(float(r[1]), float(r[2])) for r in c.xents()
          if r[6] > 0 and int(r[0]) in _ROAD_HAZ and
          abs(float(r[1]) - px) < 320]
    best, bd = 200, -1
    for yy in (90, 200, 300, 430):
        d = min((math.hypot(px - hx, yy - hy) for hx, hy in hz),
                default=1e9)
        if d > bd:
            bd, best = d, yy
    return best


def drive_dragon(c, max_t=60000):
    """The Guy Road dragon (rGuyRoad): ride the moon road under the
    cart camera, fight him face-side through the shooting windows,
    survive the devilism stages and the flag-78 chase.  His death
    checkpoints into rGuyFortress1."""
    names = room_names()
    room = names.index("rGuyRoad")
    d0 = c.deaths
    flip = 0
    for t in range(max_t):
        if c.room != room:
            break
        vx = c.view[0]
        b = c.bosses()
        flip ^= 1
        px, py, act = vx + 420, 430, 2
        if len(b) and (int(b[0][2]) != 0 or int(b[0][1]) > 0):
            ph, T = int(b[0][1]), int(b[0][2])
            dx = float(b[0][10])
            fl = int(b[0][6])
            if ph == 0:
                px, py = vx + 420, 430
            elif fl & 2:                      # dead anim
                px, py = vx + 100, 430
            elif T >= 3000:                   # flag-78 chase
                px, py = vx + 110, 474
            elif T < 0:                       # devilism stages
                px, py = (vx + 60, 474) if T <= -2000 else (vx + 700, 474)
            else:
                wps = [w for w in _alive(c, XC_WEAK) if float(w[1]) > -500]
                engaged = False
                if wps:
                    wx, wy = float(wps[0][1]), float(wps[0][2])
                    face_r = float(b[0][9]) > 0
                    if face_r:
                        px = min(max(wx + 250, dx + 380), vx + 770)
                    else:
                        px = max(min(wx - 250, dx - 260), vx + 30)
                    py = min(max(wy - 2 + (8 if t % 16 < 8 else -10),
                                 40), 520)
                    fires = [f for f in _alive(c, XC_DFIRE)
                             if abs(float(f[1]) - px) < 320]
                    if fires:
                        fy = float(fires[0][2])
                        py = min(max((fy - 150) if fy > py else (fy + 150),
                                     40), 520)
                    ok = px > dx + 372 if face_r else px < dx - 250
                    if ok:
                        act = (6 if face_r else 10) if flip else \
                              (0 if face_r else 4)
                        engaged = True
                if not engaged:
                    px, py = vx + 700, 474 if (t % 32 < 16) else 466
        else:
            rx = min(vx + 420, 23405.0)
            px, py = rx, _road_best_y(c, rx)
        c.set_state(px, py, 0, 0, 1)
        c.step(act)
        _no_death(c, d0, "dragon")
    assert names[c.room] == "rGuyFortress1", "dragon exit missing"
    assert c.gflags & FLAG_DRAGON
    # his death checkpoints the player into rGuyFortress1
    assert c.respawn_room == names.index("rGuyFortress1")


# ------------------------------------------------- Arkanoid + Sinistar

def drive_arkanoid(c, max_t=60000, chase_frames=600):
    """The rGuyFortress2 Arkanoid zone: dodge the ball while the paddle
    clears all 82 bricks; the last brick wakes the Sinistar chase."""
    d0 = c.deaths
    for t in range(max_t):
        bricks = _alive(c, XC_ARKABRICK)
        ball = _alive(c, XC_ARKABALL)
        bx, by = ((float(ball[0][1]), float(ball[0][2])) if ball
                  else (2032, 300))
        sin_ = _alive(c, XC_SINISTAR)
        cands = [(1780, 515), (2030, 515), (2280, 515), (1780, 250),
                 (2280, 250)]
        best, bd = cands[0], -1
        for p in cands:
            d = math.hypot(p[0] - bx, p[1] - by)
            if sin_ and int(sin_[0][5]) == 1:
                d = min(d, math.hypot(p[0] - float(sin_[0][1]),
                                      p[1] - float(sin_[0][2])))
            if d > bd:
                bd, best = d, p
        c.set_state(best[0], best[1], 0, 0, 1)
        c.step(2)
        _no_death(c, d0, "arkanoid")
        if not bricks:
            break
    assert not _alive(c, XC_ARKABRICK), "bricks not cleared"
    woke = False
    for k in range(chase_frames):
        s2 = _alive(c, XC_SINISTAR)
        if not s2:
            break
        if int(s2[0][5]) == 1:
            woke = True
        sx = float(s2[0][1])
        c.set_state(1780 if sx > 2030 else 2280, 515, 0, 0, 1)
        c.step(2)
        _no_death(c, d0, "sinistar chase")
    assert woke, "sinistar never woke"


# ------------------------------------------------------------ VicViper

def drive_viper(c, plan=None, max_return=1400):
    """The rGuyFortress2 Gradius section: mount the VicViper, fly the
    searched plan through the bugz/drone gauntlet, destroy the
    GradiusBoss, and ride the victory return flight home."""
    plan = VIPER_PLAN if plan is None else plan
    d0 = c.deaths

    def vstate():
        v = _alive(c, XC_VIPER)
        return int(v[0][5]) if v else -1

    for _ in range(60):
        if vstate() == 1:
            break
        c.set_state(2592, 330, 0, 0, 1)
        c.step(2)
    assert vstate() == 1, "viper mount failed"
    done = False
    for ty in plan:
        for _ in range(50):
            vs = vstate()
            if vs == 3:
                done = True
                break
            assert vs == 1, f"viper lost mid-flight (state {vs})"
            gb = _alive(c, XC_GBOSS)
            t = (float(gb[0][2]) + 10 if gb else 350) \
                if ty == "boss" else ty
            if ty == "boss" and not gb:
                done = True
                break
            h = 1 if c.x < 2612 - 16 else (-1 if c.x > 2612 + 16 else 0)
            jump = 1 if c.y > t + 3 else 0
            c.step(6 + 2 * (h + 1) + jump)
            _no_death(c, d0, "viper gauntlet")
        if done:
            break
    assert done or vstate() == 3, "gradius boss survived the plan"
    for _ in range(max_return):
        c.step(2)
        v = _alive(c, XC_VIPER)
        if not v or int(v[0][5]) != 3:
            break
    for _ in range(8):
        c.step(2)
    _no_death(c, d0, "viper return")
    assert not _alive(c, XC_GBOSS) and not _alive(c, XC_BUGZ) and \
        not _alive(c, XC_DRONE), "victory sweep incomplete"


# ------------------------------------------------------- The Guy chain

def drive_guy(c, max_t=90000):
    """GuyFirst -> TheGun -> GuyHead (rGuyBoss) through the ending
    warp.  Ends in rEnding with orb_guy set."""
    names = room_names()
    room = names.index("rGuyBoss")
    d0 = c.deaths
    flip = 0
    stage = "gf"
    pgx = pgy = None
    ph2_t0 = None
    for t in range(max_t):
        flip ^= 1
        b_gf, b_gh = _slot(c, 9), _slot(c, 10)
        px, py, act = 100, 430, 2
        if c.room != room:
            break
        if stage == "gf" and b_gf is None and _alive(c, XC_THEGUN):
            stage = "gun"
        if stage == "gf" and b_gf is not None:
            ph, T = int(b_gf[1]), int(b_gf[2])
            gx, gy = float(b_gf[10]), float(b_gf[11])
            if T < 5000:
                px, py = 100, 430
            elif ph < 2:
                side = -1 if gx > 400 else 1
                px = min(max(gx + side * 260, 40), 760)
                moving = pgx is not None and \
                    math.hypot(gx - pgx, gy - pgy) > 6
                if moving:
                    py = min(max(gy - 190, 60), 540)
                else:
                    py = min(max(gy - 6 + (12 if t % 20 < 10 else -12),
                                 60), 540)
                projs = [r for r in c.xents() if r[6] > 0 and
                         int(r[0]) in (156, 157, 158) and
                         abs(float(r[1]) - px) < 340 and
                         (float(r[1]) - px) * (1 if side < 0 else -1)
                         > -40]
                if projs:
                    fy = float(projs[0][2])
                    up = fy - 160
                    py = up if up >= 60 else fy + 160
                    py = min(max(py, 60), 540)
                pillars = [r for r in c.xents() if r[6] > 0 and
                           int(r[0]) == 124 and float(r[2]) < 640 and
                           abs(float(r[1]) - px) < 90]
                if pillars:
                    py = min(py, 430)
                act = (10 if side < 0 else 6) if flip else \
                      (4 if side < 0 else 0)
            elif ph == 2:
                settled = abs(gx - 401) < 12 and abs(gy - 577) < 12
                if ph2_t0 is None:
                    ph2_t0 = t
                if not settled or t - ph2_t0 < 70:
                    px, py = 100, 160
                else:
                    balls = [(float(r[1]), float(r[2]))
                             for r in c.xents()
                             if r[6] > 0 and int(r[0]) in (157, 158)]
                    spots = [(590, 470), (170, 470), (590, 300),
                             (170, 300), (590, 130), (330, 120)]
                    best = fallback = spots[0]
                    bd = -1
                    chosen = False
                    for p in spots:
                        d = min((math.hypot(p[0] - bx2, p[1] - by2)
                                 for bx2, by2 in balls), default=1e9)
                        if not chosen and d > 250:
                            best = p
                            chosen = True
                        if d > bd:
                            bd = d
                            fallback = p
                    px, py = best if chosen else fallback
            else:
                px, py = 100, 430
            if _alive(c, XC_THEGUN):
                stage = "gun"
        elif stage == "gun":
            guns = _alive(c, XC_THEGUN)
            if guns:
                px, py = float(guns[0][1]), float(guns[0][2]) - 8
                if int(guns[0][5]) >= 1:
                    stage = "head"
            else:
                gh = _slot(c, 10)
                if gh is not None and int(gh[2]) > 0:
                    stage = "head"
                else:
                    px, py = 400, 430
        elif stage == "head":
            gh = _slot(c, 10)
            if gh is not None and int(gh[2]) < 285:
                c.step(2)                     # cutscene: hands off
                _no_death(c, d0, "guy head cutscene")
                continue
            if gh is None:
                px, py = 400, 1150
            else:
                eyes = _alive(c, XC_GEYE)
                armed = [e for e in eyes if int(e[10]) >= 2]
                if armed:
                    e0 = armed[0]
                    ex, ey = float(e0[1]), float(e0[2])
                    px = 180 if ex <= 400 else 620
                    side = 1 if px < ex else -1
                    hzs = [(float(r[1]), float(r[2])) for r in c.xents()
                           if r[6] > 0 and
                           int(r[0]) in (156, 161, 162, 163, 164) and
                           abs(float(r[1]) - px) < 300]
                    cands = [(px, ey - 2), (px, ey - 170), (px, 1050),
                             (px, ey + 60)]
                    bestp, bd2 = cands[0], -1
                    for p2 in cands:
                        d2 = min((math.hypot(p2[0] - hx2, p2[1] - hy2)
                                  for hx2, hy2 in hzs), default=1e9)
                        if d2 > bd2:
                            bd2, bestp = d2, p2
                    px, py = bestp[0], min(max(bestp[1], 700), 1180)
                    if abs(py - ey) < 30:
                        act = (10 if side > 0 else 6) if flip else \
                              (4 if side > 0 else 0)
                else:
                    spinning = any(int(e2[5]) == 2 for e2 in eyes)
                    if spinning:
                        cyc = ([(100, 1175), (700, 1175)]
                               if int(gh[1]) < 2
                               else [(180, 1040), (620, 1040)])
                        px, py = cyc[(t // 22) % 2]
                    else:
                        hzs2 = [(float(r[1]), float(r[2]))
                                for r in c.xents() if r[6] > 0 and
                                int(r[0]) in (156, 158, 162, 163, 164)]
                        if int(gh[1]) < 2:
                            cands2 = [(407, 1175), (100, 1175),
                                      (700, 1175), (180, 1000),
                                      (620, 1000)]
                        else:
                            cands2 = [(620, 1000), (180, 1000),
                                      (620, 860), (180, 860),
                                      (407, 1050)]
                        bp2, bd3 = cands2[0], -1
                        for p3 in cands2:
                            d3 = min((math.hypot(p3[0] - a2, p3[1] - b2)
                                      for a2, b2 in hzs2), default=1e9)
                            if d3 > bd3:
                                bd3, bp2 = d3, p3
                        px, py = bp2
        if b_gf is not None:
            pgx, pgy = float(b_gf[10]), float(b_gf[11])
        c.set_state(px, py, 0, 0, 1)
        c.step(act)
        _no_death(c, d0, "guy chain")
    assert names[c.room] == "rEnding", "guy chain did not reach rEnding"
    assert c.gflags & FLAG_GUY


# ---------------------------------------------------------- Full game

def run_full_game(seed=11, env=None, verbose=False):
    """One deterministic session from the rGuy1 spawn to the completion
    event: all eight bosses, all flags, the EntranceTele gate, and the
    rEnding completion — zero deaths.  Returns a summary dict."""
    from iwanna_gym.clib import CIWanna
    from . import load_pack
    names = room_names()
    c = env
    if c is None:
        c = CIWanna.from_pack(load_pack(), seed=seed,
                              checkpoint_respawn=True,
                              start_room=names.index("rGuy1"),
                              max_steps=90000000)
        c.reset()
    c.step(2)
    log = []

    def note(msg):
        log.append((c.tick, msg, hex(c.gflags), c.deaths))
        if verbose:
            print(f"tick={c.tick:>8} deaths={c.deaths} "
                  f"gflags={hex(c.gflags):>7} {msg}")

    note("start rGuy1")
    drive_tyson(c);                     note("tyson down")
    goto(c, 4800, 1216, "rZelda")
    goto(c, 800, 960, "rGraveyard")
    goto(c, 2400, 1216, "rMechaBirdoBoss")
    drive_birdo(c);                     note("birdo down")
    goto(c, 3200, 608, "rGuyEntrance")
    goto(c, 64, 512, "rGuy1")
    goto(c, 352, 1824, "rKraidgiefLair")
    goto(c, 5248, 1824, "rKraidgiefBoss")
    drive_kraidgief(c);                 note("kraidgief down")
    goto(c, 2400, 960, "rBowserBoss")
    drive_clowncar(c);                  note("clowncar down")
    goto(c, 1600, 448, "rFactoryOutskirts")
    goto(c, 3968, 608, "rGuyEntrance")
    goto(c, 64, 512, "rGuy1")
    goto(c, 4000, 1824, "rMegaman")
    goto(c, 1952, 1824, "rMetroid")
    drive_mommy(c);                     note("mother brain down")
    goto(c, 2720, 544, "rCastlevania")
    goto(c, -32, 224, "rDraculaBoss")
    drive_dracula(c);                   note("dracula down")
    assert (c.gflags & 0x7e) == 0x7e, "six orbs required for the gate"
    goto(c, 3968, 608, "rGuyEntrance")
    goto(c, 214, 473, "rGuyRoad")       # EntranceTele: gate passes
    note("entrance gate passed")
    drive_dragon(c);                    note("dragon down")
    goto(c, 2400, 128, "rGuyLabyrinth")
    goto(c, 2400, 1632, "rGuyFortress2")
    # gradius before arkanoid: a woken Sinistar hunts the mounted
    # viper (source Collision_VicViper -> event_user(0) = die)
    drive_viper(c);                     note("gradius cleared")
    drive_arkanoid(c);                  note("arkanoid cleared")
    goto(c, 4800, 1600, "rGuyTower")
    goto(c, 800, 384, "rGuyBoss")
    drive_guy(c);                       note("the guy down")
    gflags_final = c.gflags               # completion resets the run
    comp0 = c.game_completions
    for _ in range(4):
        c.step(2)
        if c.game_completions > comp0:
            break
    note("completion")
    out = {
        "gflags": gflags_final,
        "deaths": c.deaths,
        "completions": c.game_completions,
        "last_event": c.last_event,
        "room": names[c.room],
        "log": log,
    }
    if env is None:
        c.close()
    return out
