"""Source-fidelity tests for the two ported IWBTGR 1.5.3 bosses:
MechaBirdo (rMechaBirdoBoss) and Kraidgief (rKraidgiefBoss).

The scripted fights pin the player with set_state (the test drives
positions, the engine drives everything else) and verify, against the
source GML numbers: initialization, every phase and its HP threshold,
damage routing and positional invulnerability windows, projectile
timing, death/completion sequences, progression flags, arena/room
transitions, refight skips, and deterministic replay.  A pinned
reference trace covers the full Birdo fight.
"""
from __future__ import annotations

import hashlib
import os

import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.games import iwbtgr_1_5_3 as G

needs_pack = pytest.mark.skipif(not os.path.isfile(G.PACK_PATH),
                                reason="iwbtgr pack not built locally")

# class ids (mirrors c_src/exact.h)
XC_WEAK, XC_BIRDO, XC_EGG, XC_EGGPLAT, XC_EGGHB = 96, 98, 99, 100, 101
XC_LAZA, XC_FLYGUY, XC_KG, XC_PROJ, XC_FIRE = 102, 103, 104, 105, 106
XC_BLANKA, XC_KGSPIKE, XC_KGCEIL, XC_BOLT = 107, 110, 111, 4
DEF_BIRDO, DEF_KRAIDGIEF = 2, 3
F_VULN, F_DEAD, F_INTRO = 1, 2, 4
FLAG_BIRDO, FLAG_KRAIDGIEF = 2, 3


def _env(room, seed=11, **kw):
    c = CIWanna.from_pack(G.load_pack(), seed=seed, checkpoint_respawn=True,
                          start_room=G.room_names().index(room),
                          max_steps=200000, **kw)
    c.reset()
    return c


def _alive(xe, cls):
    return [r for r in xe if int(r[0]) == cls and r[6] > 0]


# ------------------------------------------------------------- MechaBirdo

def _birdo_fight(c, hooks=None, max_t=4000):
    """The scripted Birdo kill; returns the event list."""
    names = G.room_names()
    room = names.index("rMechaBirdoBoss")
    events, last = [], 0
    for t in range(max_t):
        if c.room != room:
            events.append((t, "room-exit", names[c.room],
                           round(c.x), round(c.y)))
            break
        b = c.bosses()
        a = 2
        if len(b):
            bx, by = float(b[0][10]), float(b[0][11])
            ph = int(b[0][1])
            if ph != last:
                events.append((t, "phase", ph, float(b[0][3])))
                last = ph
            if int(b[0][6]) & F_DEAD:
                if events[-1][1] != "dead":
                    events.append((t, "dead", float(b[0][3])))
                c.set_state(400, 300, 0, 0, 1)
            else:
                wy = {1: by - 700.0, 2: by - 600.0, 3: by - 570.0}[ph]
                c.set_state(bx - 300, wy, 0, 0, 1)
                a = 8 if t % 2 == 0 else 2
        else:
            c.set_state(400, 300, 0, 0, 1)
        if hooks:
            hooks(t, c)
        c.step(a)
    return events


@needs_pack
def test_birdo_initialization():
    """Create event: placed at (704,480), repositioned to (1068,931) and
    pre-advanced 128 walk-in frames (source comment fudge); phase 1 with
    the 30-HP antenna, three weak points, the first egg + 3 platforms."""
    c = _env("rMechaBirdoBoss")
    c.step(2)
    b = c.bosses()
    assert len(b) == 1 and int(b[0][0]) == DEF_BIRDO
    assert int(b[0][1]) == 1 and float(b[0][4]) == 30.0
    # x after init: 1068 - 0.4*129 (128 pre-sim + 1 live step)
    assert abs(float(b[0][10]) - (1068 - 0.4 * 129)) < 0.01
    xe = c.xents()
    assert len(_alive(xe, XC_WEAK)) == 3
    assert len(_alive(xe, XC_EGG)) == 1
    assert len(_alive(xe, XC_EGGPLAT)) == 3
    c.close()


@needs_pack
def test_birdo_phases_damage_death_transition():
    """Full fight: 30 antenna + 15 eye + 5 mouth damage, death sink, and
    the source completion room_goto(rFactoryOutskirts) at its start."""
    c = _env("rMechaBirdoBoss", seed=3)
    ev = _birdo_fight(c)
    kinds = [(e[1], e[2] if e[1] == "phase" else None) for e in ev]
    assert ("phase", 2) in kinds and ("phase", 3) in kinds
    ph2 = next(e for e in ev if e[1] == "phase" and e[2] == 2)
    ph3 = next(e for e in ev if e[1] == "phase" and e[2] == 3)
    assert ph2[3] == 30.0                     # cumulative dmg thresholds
    assert ph3[3] == 45.0
    dead = next(e for e in ev if e[1] == "dead")
    assert dead[2] == 50.0
    exit_ = ev[-1]
    assert exit_[1] == "room-exit" and exit_[2] == "rFactoryOutskirts"
    assert (exit_[3], exit_[4]) == (49, 983)  # target playerStart
    assert c.deaths == 0
    c.close()


@needs_pack
def test_birdo_positional_invulnerability():
    """While attacking (image_index >= 1) the phase-1/2 weak points park
    at -9999 (source hitbox followers): shots during the attack window do
    no damage."""
    c = _env("rMechaBirdoBoss")
    c.step(2)
    # wait for the first attack (alarm[0]=240, anim 4 frames at 0.15)
    for t in range(400):
        b = c.bosses()
        ent = int(b[0][5])
        fr = float(c.xents()[ent][8])         # body image_index
        if fr >= 1.0:
            break
        c.set_state(200, 200, 0, 0, 1)
        c.step(2)
    d0 = float(c.bosses()[0][3])
    # shoot at the (parked) antenna position for the rest of the attack
    for t in range(20):
        b = c.bosses()
        bx, by = float(b[0][10]), float(b[0][11])
        c.set_state(bx - 300, by - 700, 0, 0, 1)
        c.step(8 if t % 2 == 0 else 2)
    assert float(c.bosses()[0][3]) == d0      # no damage while parked
    c.close()


@needs_pack
def test_birdo_projectile_timing():
    """Phase 2: BirdoLaza pairs on the 200-frame alarm[3] (spawned only
    while idle), lasers at hspeed mmf_speed(-75) = -9.375, eggs at
    eggspeed 3."""
    c = _env("rMechaBirdoBoss", seed=3)
    # drive to phase 2 with the scripted fight, then stop shooting
    names = G.room_names()
    laza_seen = []
    egg_vx = set()
    for t in range(4000):
        b = c.bosses()
        a = 2
        if len(b):
            bx, by = float(b[0][10]), float(b[0][11])
            ph = int(b[0][1])
            if ph == 1:
                c.set_state(bx - 300, by - 700, 0, 0, 1)
                a = 8 if t % 2 == 0 else 2
            else:                             # phase 2: observe only
                c.set_state(60, 100, 0, 0, 1)
                for r in _alive(c.xents(), XC_LAZA):
                    if float(r[3]) != 0:
                        assert float(r[3]) == -9.375
                fresh = [r for r in _alive(c.xents(), XC_LAZA)
                         if float(r[1]) > bx - 60]
                if fresh:
                    laza_seen.append(t)
                for r in _alive(c.xents(), XC_EGG):
                    egg_vx.add(float(r[3]))
                if len(laza_seen) > 40:
                    break
        c.step(a)
    assert laza_seen, "no lasers observed in phase 2"
    # pair-spawn events: collapse consecutive frames, gaps = 200
    starts = [laza_seen[0]]
    for t in laza_seen[1:]:
        if t - starts[-1] > 30:
            starts.append(t)
    # alarm[3] period 200; a laser pair fires only while idle, so gaps
    # are exact multiples of 200 (attack-frame alarms skip, as in source)
    gaps = [b2 - a2 for a2, b2 in zip(starts, starts[1:])]
    assert gaps and all(g % 200 == 0 for g in gaps), gaps
    assert 200 in gaps
    assert -3.0 in egg_vx                     # eggspeed 3 in phase 2
    c.close()


@needs_pack
def test_birdo_refight_skip_and_orb_flag():
    """savedata("orb_birdo"): entering the arena with the flag warps to
    rFactoryOutskirts (32,624) with no boss; the flag itself is set by
    the OrbBirdo pickup at (736,928) in rFactoryOutskirts."""
    names = G.room_names()
    c = _env("rMechaBirdoBoss")
    c.set_gflag(FLAG_BIRDO, True)
    c.attempt_reset()
    for _ in range(3):
        c.step(2)
        if c.room != names.index("rMechaBirdoBoss"):
            break
    assert names[c.room] == "rFactoryOutskirts"
    assert (round(c.x), round(c.y)) == (32, 624)
    assert len(c.bosses()) == 0
    c.close()

    c = _env("rFactoryOutskirts")
    assert not c.gflags >> FLAG_BIRDO & 1
    c.set_state(736, 920, 0, 0, 1)
    for _ in range(4):
        c.step(2)
        if c.gflags >> FLAG_BIRDO & 1:
            break
    assert c.gflags >> FLAG_BIRDO & 1
    c.close()


@needs_pack
def test_birdo_reference_trace():
    """Deterministic reference trace of the complete scripted fight
    (player + boss state each frame), pinned by checksum."""
    c = _env("rMechaBirdoBoss", seed=3)
    h = hashlib.sha256()
    names = G.room_names()
    room = names.index("rMechaBirdoBoss")
    for t in range(1500):
        if c.room != room:
            h.update(b"EXIT")
            break
        b = c.bosses()
        a = 2
        if len(b):
            bx, by = float(b[0][10]), float(b[0][11])
            ph = int(b[0][1])
            if int(b[0][6]) & F_DEAD:
                c.set_state(400, 300, 0, 0, 1)
            else:
                wy = {1: by - 700.0, 2: by - 600.0, 3: by - 570.0}[ph]
                c.set_state(bx - 300, wy, 0, 0, 1)
                a = 8 if t % 2 == 0 else 2
            h.update(f"{bx:.3f},{by:.3f},{ph},{b[0][3]:.1f};".encode())
        c.step(a)
        h.update(f"{c.x:.3f},{c.y:.3f};".encode())
    digest = h.hexdigest()
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "iwbtgr_trace_birdo.sha")
    if not os.path.isfile(fixture):
        pytest.skip("boss trace fixture not recorded yet")
    assert digest == open(fixture).read().strip()
    c.close()


# ------------------------------------------------------------- Kraidgief

def _kg_fight(c, max_t=110000, stop_after=None):
    """The scripted Kraidgief kill; returns the event list."""
    names = G.room_names()
    room = names.index("rKraidgiefBoss")
    events, last, saw_p4 = [], (-2,), False
    for t in range(max_t):
        if c.room != room:
            events.append((t, "room-exit", names[c.room],
                           round(c.x), round(c.y)))
            break
        b = c.bosses()
        a = 2
        if len(b):
            f = int(b[0][6]); ph = int(b[0][1]); intro = f & F_INTRO
            timer = int(b[0][2]); spr = int(b[0][7])
            if ph == 4:
                saw_p4 = True
            key = (ph, 1 if intro else 0)
            if key != last:
                events.append((t, "phase", ph, bool(intro),
                               float(b[0][3]), round(float(b[0][11]))))
                last = key
            xe = c.xents()
            wps = _alive(xe, XC_WEAK)
            proj = bool(_alive(xe, XC_PROJ))
            fire = bool(_alive(xe, XC_FIRE))
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
        if stop_after and stop_after(t, c, events):
            break
        c.step(a)
    return events


@needs_pack
def test_kraidgief_spawn_intro_camera():
    """The arena trigger spawns Kraidgief at (128,896); he rises at
    mmf_speed(8)=1 px/f from timer 50 to y=384 under the locked, quaking
    camera (view pinned to (0,281) + voffset)."""
    c = _env("rKraidgiefBoss")
    spawn_t = None
    for t in range(700):
        b = c.bosses()
        if len(b):
            if spawn_t is None:
                spawn_t = t
                assert float(b[0][10]) == 128.0
                assert float(b[0][11]) == 896.0
                assert int(b[0][6]) & F_INTRO
            c.set_state(400, 165, 0, 0, 1)
            vx, vy = c.view
            assert vx == 0.0 and 281.0 <= vy <= 296.0
            if not int(c.bosses()[0][6]) & F_INTRO:
                break
        c.step(2)
    assert spawn_t is not None
    b = c.bosses()
    assert float(b[0][11]) == 384.0           # intro parks at y=384
    assert int(b[0][2]) >= 2000               # timer jumps to 2000
    c.close()


@needs_pack
def test_kraidgief_vulnerability_windows():
    """Shots land only during roars (vuln windows): outside them the
    hitbox collects nothing (and the body deflects bullets instead)."""
    c = _env("rKraidgiefBoss")
    # reach phase 0 post-intro
    for t in range(700):
        b = c.bosses()
        if len(b):
            c.set_state(400, 165, 0, 0, 1)
            if not int(b[0][6]) & F_INTRO:
                break
        c.step(2)
    # post-intro timer is 2000; the first roar opens at 2020 — the
    # window [2001..2019] is guaranteed non-vulnerable: shots there must
    # count nothing (they ricochet off the body instead)
    deflected = False
    d0 = float(c.bosses()[0][3])
    for t in range(14):
        b = c.bosses()
        xe = c.xents()
        wps = _alive(xe, XC_WEAK)
        wx, wy = float(wps[0][1]), float(wps[0][2])
        c.set_state(wx - 250, wy, 0, 0, 1)
        c.step(10 if t % 2 == 0 else 4)
        for r in c.entities(64):
            if int(r[0]) == 12 and float(r[4]) != 0:
                deflected = True                # body ricochet observed
    assert float(c.bosses()[0][3]) == d0 == 0.0
    assert deflected
    # then the roar at timer 2020 (80-frame window): damage lands
    for t in range(160):
        b = c.bosses()
        xe = c.xents()
        wps = _alive(xe, XC_WEAK)
        wx, wy = float(wps[0][1]), float(wps[0][2])
        c.set_state(wx - 250, wy, 0, 0, 1)
        c.step(10 if t % 2 == 0 else 4)
        if float(c.bosses()[0][3]) > 0:
            break
    assert float(c.bosses()[0][3]) > 0
    c.close()


@needs_pack
def test_kraidgief_full_fight_progression():
    """The whole fight: intro -> phase 0 (15 dmg arms the lariat
    transition) -> lariat clears the ceiling -> phase 1 (25) -> phase 2
    charge + AngryStand (120) -> death sequence clears the floor spikes
    -> orb sets orb_kraidgief -> exit warp to rMegaman (17,407)."""
    c = _env("rKraidgiefBoss")
    ev = _kg_fight(c)
    phases = [(e[2], e[3]) for e in ev if e[1] == "phase"]
    assert (0, True) in phases                # intro
    assert (0, False) in phases
    assert (1, False) in phases and (2, False) in phases
    assert (4, False) in phases
    p1 = next(e for e in ev if e[1] == "phase" and e[2] == 1)
    assert p1[5] == 64                        # lariat parks at y=64
    p2 = next(e for e in ev if e[1] == "phase" and e[2] == 2)
    assert p2[4] == 25.0                      # cumulative damage threshold
    p4 = next(e for e in ev if e[1] == "phase" and e[2] == 4)
    assert p4[4] == 120.0
    exit_ = ev[-1]
    assert exit_[1] == "room-exit" and exit_[2] == "rMegaman"
    assert (exit_[3], exit_[4]) == (17, 407)
    assert c.gflags >> FLAG_KRAIDGIEF & 1     # orb collected
    assert c.deaths == 0
    c.close()


@needs_pack
def test_kraidgief_phase1_state_and_ceiling():
    """After the lariat: every KraidgiefCeiling solid is destroyed, the
    camera unlocks (follows the player), and phase-1 attack cycles run
    (walk starts at timer 600125 within each 500-frame loop)."""
    c = _env("rKraidgiefBoss")

    reached = {}

    def stop(t, cc, ev):
        b = cc.bosses()
        if len(b) and int(b[0][1]) == 1 and not reached:
            reached["t"] = t
        return len(b) > 0 and int(b[0][1]) == 2
    _kg_fight(c, stop_after=stop)
    assert reached
    assert not _alive(c.xents(), XC_KGCEIL)
    # camera follows the player once unlocked (park above the body sweep)
    c.set_state(900, 40, 0, 0, 1)
    c.step(2)
    c.set_state(900, 40, 0, 0, 1)
    c.step(2)
    vx, vy = c.view
    assert len(c.bosses()) == 1               # fight still running
    assert vx == 500.0                        # clamp(900-400, 0, 800)
    assert vy == 0.0                          # clamp(40-304, 0, 281)
    c.close()


@needs_pack
def test_kraidgief_grab_kill():
    """Phase 1 with no eye damage: he walks to the left wall and the
    grab closes -> the SPD piledriver kill (compressed to the grab-close
    frame; the death counts and the room resets)."""
    c = _env("rKraidgiefBoss")
    phases = set()

    def stop(t, cc, ev):
        b = cc.bosses()
        if len(b):
            phases.add(int(b[0][1]))
            if int(b[0][1]) == 1:
                cc.set_state(700, 100, 0, 0, 1)   # stop interfering
        return cc.deaths > 0
    # drive phase 0 normally, then idle through phase 1
    ev = _kg_fight(c, stop_after=stop)
    assert 3 in phases                        # the grab phase ran
    assert c.deaths == 1
    c.close()


@needs_pack
def test_kraidgief_phase2_blankas_and_fire():
    """Phase 2 with the player low: Blanka waves spawn on the 300-frame
    cadence (up to 5), then the giant fire (down variant for a low
    player) — all tier/aim decisions read the live player position."""
    c = _env("rKraidgiefBoss")

    seen = {"blanka": 0, "fire": 0}

    def stop(t, cc, ev):
        b = cc.bosses()
        if len(b) and int(b[0][1]) == 2:
            if int(b[0][7]) in (6, 7):            # AngryStand / Fire
                cc.set_state(1200, 600, 0, 0, 1)  # low + far right
            xe = cc.xents()
            seen["blanka"] = max(seen["blanka"], len(_alive(xe, XC_BLANKA)))
            if _alive(xe, XC_FIRE):
                seen["fire"] += 1
                return True
        return False
    _kg_fight(c, stop_after=stop)
    assert seen["blanka"] >= 1
    assert seen["fire"] >= 1
    c.close()


@needs_pack
def test_kraidgief_won_arena_teardown():
    """Entering with orb_kraidgief set: the trigger's create code clears
    the whole arena (ceiling, destructibles, spikes, floor, trigger) and
    unlocks the camera — a plain corridor to the exit warp remains."""
    names = G.room_names()
    c = _env("rKraidgiefBoss")
    c.set_gflag(FLAG_KRAIDGIEF, True)
    c.attempt_reset()
    xe = c.xents()
    assert not _alive(xe, XC_KGCEIL)
    assert not _alive(xe, XC_KGSPIKE)
    assert not _alive(xe, XC_BOLT)
    # walk the floor to the exit warp: no boss ever spawns
    for t in range(400):
        c.set_state(min(1616, c.x + 6), 780, 0, 0, 1)
        c.step(2)
        if c.room != names.index("rKraidgiefBoss"):
            break
    assert names[c.room] == "rMegaman"
    assert len(c.bosses()) == 0
    c.close()


@needs_pack
def test_boss_fights_deterministic_replay():
    """Same seed + same script => identical fights (both bosses)."""
    def run_birdo():
        c = _env("rMechaBirdoBoss", seed=3)
        ev = _birdo_fight(c, max_t=1500)
        out = (ev, round(c.x, 4), round(c.y, 4), c.room, int(c.gflags))
        c.close()
        return out

    def run_kg():
        c = _env("rKraidgiefBoss")
        ev = _kg_fight(c, max_t=2200)
        b = c.bosses()
        out = (ev, round(c.x, 4), round(c.y, 4),
               b.tolist() if len(b) else [])
        c.close()
        return out
    assert run_birdo() == run_birdo()
    assert run_kg() == run_kg()
