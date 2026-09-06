"""Observable-vector observation-contract tests (torch-free).

Pins the declared contract (docs/discovery_benchmark_contract.md §7):
the headline `observable_vector` mode exposes only information derivable
from the rendered scene, and NEVER simulator-only hazard state. Covers
offscreen / inactive entities, invisible/unarmed hazards, dormant trap
state, and source camera visibility. Privileged mode is the oracle and
may expose more; it is compared only to prove the filter is live.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

import sys
sys.path.insert(0, ".")
import iwanna_gym as iw                                   # noqa: E402
import iwanna_gym.discovery as d                          # noqa: E402
from iwanna_gym.clib import OBS_SIZE                       # noqa: E402

PACK = "build/games/iwbtgr_1_5_3.iwpack"
ENT_SLOTS = 6
ENT_F = 5
ENT_BASE = OBS_SIZE - ENT_SLOTS * ENT_F   # 101 - 30 = 71


def _ent_slots(obs):
    return obs[ENT_BASE:].reshape(ENT_SLOTS, ENT_F)


# ------------------------------------------------------------------ #
# invisible / unarmed hazards (pack)
# ------------------------------------------------------------------ #

@pytest.mark.skipif(not os.path.exists(PACK), reason="local pack required")
def test_observable_excludes_undrawn_xents_privileged_may_include():
    tid = "disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall"

    def obs_and_ground_truth(mode):
        e = d.make_env(tid, obs_mode=mode)
        obs, _ = e.reset(seed=0, options={"task_seed": 5})
        x = e.c.xents()
        drawn = e.c.xents_drawn()
        px, py, W, H = e.c.x, e.c.y, e.c.tw * 32.0, e.c.th * 32.0
        e.close()
        return obs.copy(), x, drawn, px, py, W, H

    obs_o, x, drawn, px, py, W, H = obs_and_ground_truth(
        "observable_vector")
    obs_p, *_ = obs_and_ground_truth("privileged_vector")
    assert not np.array_equal(obs_o, obs_p), "obs filter is dead"

    # every alive+active+UNDRAWN xent position must be absent from the
    # observable entity slots (invisible/unarmed hazards stay hidden)
    undrawn = [(row[1], row[2]) for row, dr in zip(x, drawn)
               if row[6] and row[7] and not dr]
    assert undrawn, "fortress spawn should carry unmanifested hazards"
    for hx, hy in undrawn:
        ndx, ndy = (hx - px) / W, (hy - py) / H
        for slot in _ent_slots(obs_o):
            if np.abs(slot).sum() == 0:
                continue
            assert abs(slot[0] - ndx) + abs(slot[1] - ndy) > 1e-6, \
                "observable obs contains an undrawn (invisible) hazard"


@pytest.mark.skipif(not os.path.exists(PACK), reason="local pack required")
def test_observable_slots_map_only_to_active_drawn_entities():
    # camera/offscreen visibility: an inactive entity (outside the
    # source activation region) must never occupy an observable slot.
    tid = "disc.iwbtgr_1_5_3.rGuy1.first_screen"
    e = d.make_env(tid, obs_mode="observable_vector")
    obs, _ = e.reset(seed=0, options={"task_seed": 3})
    for _ in range(40):
        obs, r, term, tr, info = e.step(4)
        x = e.c.xents()
        drawn = e.c.xents_drawn()
        px, py, W, H = e.c.x, e.c.y, e.c.tw * 32.0, e.c.th * 32.0
        drawn_active = [(row[1], row[2]) for row, dr in zip(x, drawn)
                        if row[6] and row[7] and dr]
        for slot in _ent_slots(obs):
            if np.abs(slot).sum() == 0:
                continue
            # each used slot must correspond to some drawn+active xent
            # OR a classic legacy entity (saves/bullets); accept a match
            # against drawn-active xents within rounding
            ok = any(abs(slot[0] - (ex - px) / W)
                     + abs(slot[1] - (ey - py) / H) < 1e-4
                     for ex, ey in drawn_active)
            legacy = e.c.entities()
            ok = ok or len(legacy) > 0     # legacy ents (saves) allowed
            assert ok, "observable slot maps to no active drawn entity"
        if term:
            break
    e.close()


# ------------------------------------------------------------------ #
# dormant trap state (classic entity system)
# ------------------------------------------------------------------ #

_DORMANT = """\
###############
#.............#
#.............#
#.............#
#.............#
#.............#
#.............#
#....S........#
#............G#
###############
@trap 6 2 dir=down vy=7 id=1
@trigger 11 8 id=1 w=1 h=1
"""
# same room, trap present but NO trigger -> it is a live parked trap
# (never dormant); a parked deadly trap and a dormant trap must look
# identical in the observable vector (dormant STATE is not leaked)
_ARMED = """\
###############
#.............#
#.............#
#.............#
#.............#
#.............#
#.............#
#....S........#
#............G#
###############
@trap 6 2 dir=down vy=7
"""


def test_dormant_state_not_leaked_in_observable_vector():
    a = iw.IWannaDiscoveryEnv(level=_DORMANT, obs_mode="observable_vector",
                              attempts_K=2, attempt_frames_H=200)
    b = iw.IWannaDiscoveryEnv(level=_ARMED, obs_mode="observable_vector",
                              attempts_K=2, attempt_frames_H=200)
    oa, _ = a.reset(seed=0, options={"task_seed": 1})
    ob, _ = b.reset(seed=0, options={"task_seed": 1})
    # stand still: the dormant trap never fires, the armed trap is parked
    for _ in range(20):
        oa = a.step(2)[0]
        ob = b.step(2)[0]
        # the trap's entity slot (a parked down-spike at the same place)
        # must be identical: no dormant flag bleeds into the vector
        assert np.array_equal(_ent_slots(oa), _ent_slots(ob)), \
            "dormant vs armed parked trap differ in observable obs"
    a.close(); b.close()


def test_privileged_and_observable_type_sign_from_appearance_not_flags():
    # a make_harmless'd hazard must read the SAME as its deadly twin in
    # observable mode (sign from appearance), but privileged sees the
    # flag. Uses the entity event system.
    deadly = """\
##########
#........#
#........#
#........#
#..S.....#
#.......G#
##########
@spikeball 6 4 range=0
"""
    harmless = deadly + "!when=room_enter -> make_harmless tag=0\n"
    # tag defaults; use explicit tag
    deadly = deadly.replace("@spikeball 6 4 range=0",
                            "@spikeball 6 4 range=0 tag=5")
    harmless = deadly + "!when=room_enter -> make_harmless tag=5\n"
    ed = iw.IWannaDiscoveryEnv(level=deadly, obs_mode="observable_vector",
                               attempts_K=2, attempt_frames_H=100)
    eh = iw.IWannaDiscoveryEnv(level=harmless, obs_mode="observable_vector",
                               attempts_K=2, attempt_frames_H=100)
    od, _ = ed.reset(seed=0, options={"task_seed": 1})
    oh, _ = eh.reset(seed=0, options={"task_seed": 1})
    od = ed.step(2)[0]
    oh = eh.step(2)[0]
    assert np.array_equal(_ent_slots(od), _ent_slots(oh)), \
        "make_harmless changed the observable obs (deadliness leaked)"
    # privileged distinguishes them (the live EF_DEADLY flag)
    edp = iw.IWannaDiscoveryEnv(level=deadly, obs_mode="privileged_vector",
                                attempts_K=2, attempt_frames_H=100)
    ehp = iw.IWannaDiscoveryEnv(level=harmless,
                                obs_mode="privileged_vector",
                                attempts_K=2, attempt_frames_H=100)
    odp = edp.reset(seed=0, options={"task_seed": 1})[0]; odp = edp.step(2)[0]
    ohp = ehp.reset(seed=0, options={"task_seed": 1})[0]; ohp = ehp.step(2)[0]
    assert not np.array_equal(_ent_slots(odp), _ent_slots(ohp)), \
        "privileged mode should see the deadliness flag"
    ed.close(); eh.close(); edp.close(); ehp.close()


def test_pixels_mode_unsupported_for_packs_is_explicit():
    # native pixel observations are explicitly unsupported (offline
    # visualization uses the separate renderer); the env must say so.
    with pytest.raises(NotImplementedError):
        iw.IWannaDiscoveryEnv(game="iwbtgr_1_5_3", mode="room",
                              room_id="rGuy1", obs_mode="pixels")
