"""Entity-system tests: behaviors, interactions, determinism, and scale."""
import time

import numpy as np
import pytest

from iwanna_gym.clib import OBS_SIZE, CIWanna

# 12x8 sealed test room, floor on the bottom row, start on the left.
ROOM = (
    "############\n"
    "#..........#\n"
    "#..........#\n"
    "#..........#\n"
    "#..........#\n"
    "#..........#\n"
    "#.S......G.#\n"
    "############\n"
)

IDLE, RIGHT = 2, 4


def make(text: str, **kw) -> CIWanna:
    kw.setdefault("max_steps", 100000)
    kw.setdefault("reward_mode", 0)
    c = CIWanna(text, seed=kw.pop("seed", 5), **kw)
    c.reset()
    return c


def test_obs_size_includes_entities():
    assert OBS_SIZE == 8 + 63 + 30  # base + 7x9 tiles + 6 entities x 5 feats


def test_platform_land_and_carry():
    c = make(ROOM + "@platform 5 4 vx=1 range=48\n")
    # drop the player onto the platform (center x=176, top y=136)
    c.set_state(176, 100, 0, 0, 1)
    for _ in range(30):
        c.step(IDLE)
    ents = c.entities()
    plat = ents[ents[:, 0] == 1][0]
    # standing on top: feet (y+8) one px above platform top (py-8)
    assert abs((c.y + 8) - (plat[2] - 8 - 1)) < 0.6
    x0 = c.x
    for _ in range(20):
        c.step(IDLE)
    # carried horizontally without pressing any direction
    assert abs(c.x - x0) > 10
    assert c.deaths == 0


def test_platform_restores_double_jump():
    c = make(ROOM + "@platform 5 4\n")
    c.set_state(176, 100, 0, 0, 2)   # air jump spent
    for _ in range(30):
        c.step(IDLE)
    assert c.djump == 1               # landing on the platform restored it


def test_trigger_fires_trap_and_kills():
    # dormant ceiling trap above the corridor; trigger zone spans the room
    txt = ROOM + (
        "@trap 6 1 dir=down vy=8 id=7\n"
        "@trigger 4 4 id=7 w=1 h=6\n"
    )
    c = make(txt)
    ents = c.entities()
    trap = ents[ents[:, 0] == 4][0]
    assert trap[6] == 1.0             # dormant before the trigger
    died = False
    for i in range(300):
        c.step(RIGHT if c.x < 200 else IDLE)
        ents = c.entities()
        trap = ents[ents[:, 0] == 4]
        if len(trap) and trap[0][6] == 0.0 and not died:
            assert trap[0][4] == 8.0  # vy applied on fire
        if c.last_event == 1:
            died = True
            break
    assert died, "falling trap should kill the player"


def test_trap_deadly_while_dormant():
    # dormant trap sitting directly in the corridor at head height
    c = make(ROOM + "@trap 4 6 dir=up id=9\n")
    died = False
    for _ in range(60):
        c.step(RIGHT)
        if c.last_event == 1:
            died = True
            break
    assert died, "dormant traps must still be deadly"


def test_shooter_projectile_kills():
    # shooter on the right wall firing left along the corridor
    c = make(ROOM + "@shooter 10 6 dir=left period=30 speed=4\n")
    died = False
    for _ in range(200):
        c.step(IDLE)
        if c.last_event == 1:
            died = True
            break
    assert died, "projectile should reach and kill the idle player"


def test_projectiles_deactivate_offscreen():
    c = make(ROOM + "@shooter 10 1 dir=up period=10 speed=6\n")
    for _ in range(300):
        c.step(IDLE)
    # projectiles fly out of the room and must be culled, not accumulate
    assert c.ent_count <= 4


def test_save_and_checkpoint_respawn():
    # save point next to the start, spike wall further right
    txt = (
        "############\n"
        "#..........#\n"
        "#..........#\n"
        "#..........#\n"
        "#..........#\n"
        "#..........#\n"
        "#.S....^.G.#\n"
        "############\n"
        "@save 4 6\n"
    )
    c = make(txt, checkpoint_respawn=True)
    for _ in range(20):               # walk over the save point
        c.step(RIGHT)
    rx, ry = c.respawn
    assert abs(rx - 4 * 32 - 16) < 1  # respawn moved to the save column
    deaths_before = c.deaths
    terminated = False
    for _ in range(100):              # run into the spike
        c.step(RIGHT)
        if c.term[0]:
            terminated = True
        if c.deaths > deaths_before:
            break
    assert c.deaths == deaths_before + 1
    assert not terminated, "checkpoint death must not terminate the episode"
    assert abs(c.x - rx) < 1          # back at the save point


def test_death_still_terminates_without_checkpoint_mode():
    txt = ROOM.replace("#.S......G.#", "#.S..^...G.#")
    c = make(txt, checkpoint_respawn=False)
    terminated = False
    for _ in range(100):
        c.step(RIGHT)
        if c.term[0]:
            terminated = True
            break
    assert terminated


def test_warp_teleports():
    c = make(ROOM + "@warp 4 6 gx=8 gy=2\n")
    for _ in range(40):
        c.step(RIGHT)
        if c.x > 8 * 32 - 16 and c.y < 4 * 32:
            break
    assert abs(c.x - (8 * 32 + 16)) < 4
    assert c.y < 4 * 32


def test_entities_in_observations():
    c = make(ROOM + "@spikeball 5 5 vx=2 range=32\n")
    obs = c.obs.copy()
    ent_feats = obs[71:]
    assert ent_feats.shape == (30,)
    assert np.any(ent_feats != 0), "spikeball must appear in the obs tail"
    # deadly entity encodes a negative signed type
    types = ent_feats.reshape(6, 5)[:, 4]
    assert types.min() < 0
    # empty room pads with zeros
    c2 = make(ROOM)
    assert not np.any(c2.obs[71:])


def test_deterministic_replay():
    txt = ROOM + (
        "@platform 4 3 vx=1 range=40\n"
        "@spikeball 7 4 vy=2 range=48\n"
        "@shooter 10 2 dir=left period=17 speed=3\n"
        "@trap 8 1 dir=down vy=6 id=1\n"
        "@trigger 6 4 id=1 w=1 h=6\n"
    )
    rng = np.random.default_rng(123)
    actions = rng.integers(0, 6, 600)

    def rollout():
        c = make(txt, seed=42)
        traj = []
        for a in actions:
            c.step(int(a))
            ents = c.entities()
            traj.append((c.x, c.y, c.last_event, ents.tobytes()))
        c.close()
        return traj

    t1, t2 = rollout(), rollout()
    assert t1 == t2, "same seed + actions must reproduce identical trajectories"


def test_thousand_entities_cheap():
    # 40x20 room packed with >1000 moving entities
    rows = ["#" * 40]
    rows += ["#" + "." * 38 + "#" for _ in range(18)]
    rows += ["#" * 40]
    txt = "\n".join(rows) + "\n"
    lines = []
    for n in range(1050):             # entities may overlap; that is fine
        tx = 2 + n % 35
        ty = 2 + (n // 35) % 15
        kind = ("spikeball", "platform", "projectile")[n % 3]
        extra = "vx=1 range=16" if kind != "projectile" else "vx=0.5 grav=0"
        lines.append(f"@{kind} {tx} {ty} {extra}")
    txt += "\n".join(lines) + "\n"
    c = make(txt + "@save 2 17\n", checkpoint_respawn=True)
    assert c.ent_count >= 1000
    steps = 20000
    start = time.perf_counter()
    for _ in range(steps):
        c.step(IDLE)
    dt = time.perf_counter() - start
    sps = steps / dt
    print(f"\n1000+ entities: {sps:,.0f} steps/s")
    assert sps > 5000, f"1000-entity stepping too slow: {sps:.0f} steps/s"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
