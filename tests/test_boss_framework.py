"""Unit tests for the reusable boss framework (c_src/boss/), driven by the
synthetic XB_BOSS_TEST definition so no game content is involved: a tiny
pack is compiled around the boss with a weak point, an attack state
machine (timer-spawned projectiles), two HP-gated phases, invulnerability
windows, a death event that sets a progression flag, and seeded behavior.
"""
from __future__ import annotations

import numpy as np
import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.gamepack import compile_pack
from tools.importers import synthetic

import os
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "synthetic_src")

# mirrors c_src/exact.h (order-exact)
XB_WEAKBOX, XB_BOSS_TEST, XB_LAZA = 96, 97, 102
XEF_KILLER, XEF_FORCE_ACTIVE = 1, 16
IWXB_DEF_TEST = 1

HP1, HP2, PERIOD, FLAG, IFRAMES = 3, 2, 50, 7, 30


def _rect_mask(w, h, ox, oy):
    return {"w": w, "h": h, "ox": ox, "oy": oy, "bl": 0, "bt": 0,
            "br": w - 1, "bb": h - 1, "shape": 0, "rows": []}


def _pack(iframes=IFRAMES, period=PERIOD):
    doc = synthetic.extract(FIXTURE, game_id="fixture_quest")
    boss = {"cls": XB_BOSS_TEST, "mask": 0, "x": 420.0, "y": 343.0,
            "xs": 1.0, "ys": 1.0, "tag": 0, "flags": XEF_FORCE_ACTIVE,
            "p": [0, 1, HP1, HP2, period, FLAG, iframes, -1, 2.5, 0]}
    doc["exact"] = {
        "masks": [_rect_mask(32, 32, 16, 16), _rect_mask(16, 8, 0, 4)],
        "ops": [],
        "templates": [
            {"cls": XB_WEAKBOX, "mask": 0, "xs": 1.0, "ys": 1.0,
             "flags": 0, "p": [0.0] * 10},
            {"cls": XB_LAZA, "mask": 1, "xs": 1.0, "ys": 1.0,
             "flags": XEF_KILLER, "p": [0.0] * 10},
        ],
        "keys": [],
        "rooms": [
            {"xents": [boss], "camera": 0, "always_active": 1,
             "enter_ops": [0, 0]},
            {"xents": [], "camera": 0, "always_active": 0,
             "enter_ops": [0, 0]},
        ],
        "hb": [-5, -12, 5, 8],
        "flags": 1,
    }
    return compile_pack(doc).data


def _env(**kw):
    c = CIWanna.from_pack(_pack(**kw), seed=9, checkpoint_respawn=True,
                          max_steps=100000)
    c.reset()
    return c


def _pin_and_shoot(c, t, bx, by):
    """Pin left of the weak point (boss y - 32) and fire right."""
    c.set_state(bx - 200, by - 32, 0, 0, 1)
    return 10 if t % 8 == 0 else 4


def test_slot_initialization():
    c = _env()
    c.step(2)
    b = c.bosses()
    assert len(b) == 1
    assert int(b[0][0]) == IWXB_DEF_TEST
    assert int(b[0][1]) == 1                  # phase
    assert b[0][4] == HP1                     # stage hp
    # weak point spawned and following the body (moving hitbox)
    wps = [r for r in c.xents() if int(r[0]) == XB_WEAKBOX and r[6] > 0]
    assert len(wps) == 1
    for _ in range(3):
        c.step(2)
    wp = [r for r in c.xents() if int(r[0]) == XB_WEAKBOX and r[6] > 0][0]
    assert wp[1] == 420.0 and wp[2] == 343.0 - 32.0
    c.close()


def test_attack_state_machine_timing():
    """Projectiles fire on the alarm period exactly (phase 1: PERIOD)."""
    c = _env()
    seen = []
    for t in range(PERIOD * 5 + 10):
        c.set_state(80, 200, 0, 0, 1)     # out of the projectile row
        c.step(2)
        # a fresh projectile has moved exactly one 2.5px step from 404
        if any(int(r[0]) == XB_LAZA and r[6] > 0 and
               401.0 <= float(r[1]) <= 404.0 for r in c.xents()):
            seen.append(t)
    assert len(seen) >= 4
    gaps = [b - a for a, b in zip(seen, seen[1:])]
    assert all(g == PERIOD for g in gaps), gaps
    c.close()


def test_damage_phase_transitions_and_death_flag():
    c = _env(iframes=0)
    c.step(2)                                 # slot materializes on step 1
    phases = set()
    flag_at_death = None
    for t in range(4000):
        b = c.bosses()
        if not len(b):
            flag_at_death = bool(c.gflags >> FLAG & 1)
            break
        phases.add(int(b[0][1]))
        a = _pin_and_shoot(c, t, float(b[0][10]), float(b[0][11]))
        c.step(a)
    assert phases == {1, 2}
    assert flag_at_death is True
    # slot released; body gone
    assert len(c.bosses()) == 0
    assert not any(int(r[0]) == XB_BOSS_TEST and r[6] > 0
                   for r in c.xents())
    c.close()


def test_invulnerability_window():
    """With a 30-frame i-frame window, damage lands at most once per
    window even under constant fire."""
    c = _env(iframes=30)
    c.step(2)
    hp_drops = []
    last_hp = HP1
    for t in range(700):
        b = c.bosses()
        if not len(b) or int(b[0][1]) != 1:
            break
        hp = float(b[0][4])
        if hp < last_hp:
            hp_drops.append(t)
            last_hp = hp
        a = _pin_and_shoot(c, t, float(b[0][10]), float(b[0][11]))
        c.step(a)
    assert len(hp_drops) >= 2
    gaps = [b2 - a2 for a2, b2 in zip(hp_drops, hp_drops[1:])]
    assert all(g >= 30 for g in gaps), gaps
    c.close()


def test_boss_death_resets_with_room():
    """Death/retry rebuilds the fight from the pack (slot, HP, phase)."""
    c = _env(iframes=0)
    c.step(2)
    for t in range(300):
        b = c.bosses()
        if len(b) and float(b[0][4]) < HP1:
            break
        a = _pin_and_shoot(c, t, 420, 343)
        c.step(a)
    assert float(c.bosses()[0][4]) < HP1
    c.attempt_reset()
    c.step(2)
    b = c.bosses()
    assert len(b) == 1 and float(b[0][4]) == HP1 and int(b[0][1]) == 1
    c.close()


def test_deterministic_replay():
    def run():
        c = _env()
        traj = []
        for t in range(600):
            b = c.bosses()
            a = 2
            if len(b):
                a = _pin_and_shoot(c, t, float(b[0][10]), float(b[0][11]))
            c.step(a)
            row = b.tolist() if len(b) else []
            traj.append((c.x, c.y, row,
                         sum(1 for r in c.xents() if r[6] > 0)))
        c.close()
        return traj
    assert run() == run()


def test_no_boss_no_slots():
    """A room with no boss keeps n_boss == 0 (the overhead gate)."""
    c = CIWanna.from_pack(_pack(), seed=9, start_room=1,
                          checkpoint_respawn=True)
    c.reset()
    for _ in range(50):
        c.step(2)
    assert len(c.bosses()) == 0
    c.close()
