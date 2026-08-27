"""Gymnasium environments over the IWanna C core.

- IWannaEnv:     flat float32 obs (101,), Discrete(6) actions
- IWannaGoalEnv: goal-conditioned dict obs (observation/achieved_goal/desired_goal)
                 with compute_reward() for HER-style relabeling
- PixelObsWrapper: RGB pixel observations rendered in numpy

Action encoding (matches the C core):
    action = 2 * (h + 1) + jump_held,  h in {-1, 0, +1}
    0: left          1: left  + jump held
    2: idle          3: idle  + jump held
    4: right         5: right + jump held
Jump press/release edges are computed inside the core from consecutive
jump_held values, replicating GameMaker's keyboard press/release events.
"""
from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .clib import NUM_ACTIONS, OBS_SIZE, CIWanna
from .levels import load_level
from .render import TILE, downsample, render_frame, render_tiles

# goal-reach test in C is a box overlap: player hitbox (11x20) vs 32x32 goal
# box. Center-to-center reach distance is at most ~ (16+5.5, 16+10) px.
GOAL_REACH_X = 16 + 5.5
GOAL_REACH_Y = 16 + 10.0


class IWannaEnv(gym.Env):
    """Single-screen fangame platforming with exact GM8 fangame physics."""

    metadata = {"render_modes": ["rgb_array"], "render_fps": 50}

    def __init__(
        self,
        level: str = "gaps",
        max_steps: int = 1500,
        reward_mode: str = "dense",
        death_penalty: float = 1.0,
        random_goal: bool = False,
        checkpoint_respawn: bool = False,
        render_mode: str | None = None,
        pack: str | bytes | None = None,
        game: str | None = None,
        mode: str = "full_game",
        room_id: str | int | None = None,
        difficulty: str | int = 0,
    ):
        super().__init__()
        # Exact-game construction:
        #   IWannaEnv(game="iwbtgr_1_5_3", mode="full_game")
        #   IWannaEnv(game="iwbtgr_1_5_3", mode="room", room_id="rGuyLabyrinth")
        # `difficulty` gates difficulty-specific saves exactly as the source
        # does ("medium"/"hard"/"very_hard"/"impossible" or 0..3).
        self._start_room: int | None = None
        self._difficulty: int = 0
        if game is not None:
            from .games import get_game
            gmod = get_game(game)
            if pack is None:
                pack = gmod.load_pack()
            if isinstance(difficulty, str):
                difficulty = gmod.DIFFICULTIES[difficulty]
            self._difficulty = int(difficulty)
            if mode == "room":
                if room_id is None:
                    raise ValueError("mode='room' requires room_id")
                self._start_room = gmod.room_index(room_id)
            elif mode != "full_game":
                raise ValueError(f"unknown mode {mode!r}")
            self.level_name = f"{game}:{mode}" + (
                f":{room_id}" if room_id is not None else "")
        # pack: a compiled .iwpack game (path or bytes) built offline by
        # `python -m tools.iwimport compile` — see docs/gamepack_format.md.
        # When given, `level` is ignored and the env may span multiple rooms
        # (info["room"], info["room_transitions"]).
        self._pack_data: bytes | None = None
        if pack is not None:
            if isinstance(pack, str):
                with open(pack, "rb") as f:
                    self._pack_data = f.read()
            else:
                self._pack_data = bytes(pack)
            if game is None:
                self.level_name = "<pack>"
            self.level_text = ""
        else:
            self.level_name = level
            self.level_text = load_level(level) if "\n" not in level else level
        self._cfg = dict(
            max_steps=max_steps,
            reward_mode={"sparse": 0, "dense": 1}[reward_mode],
            death_penalty=death_penalty,
            random_goal=random_goal,
            checkpoint_respawn=checkpoint_respawn,
        )
        self.render_mode = render_mode
        self.c: CIWanna | None = None
        self._base_img: np.ndarray | None = None

        self.observation_space = spaces.Box(-1.0, 1.0, (OBS_SIZE,), np.float32)
        self.action_space = spaces.Discrete(NUM_ACTIONS)

    # -- gym api --
    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if self.c is None:
            cseed = int(self.np_random.integers(1, 2**63 - 1))
            if self._pack_data is not None:
                self.c = CIWanna.from_pack(
                    self._pack_data, seed=cseed,
                    start_room=self._start_room,
                    difficulty=self._difficulty, **self._cfg)
            else:
                self.c = CIWanna(self.level_text, seed=cseed, **self._cfg)
        self.c.reset()
        return self.c.obs.copy(), self._info()

    def step(self, action: int):
        self.c.step(int(action))
        terminated = bool(self.c.term[0])
        reward = float(self.c.rew[0])
        # C core auto-resets on terminal (obs already belongs to the next
        # episode); Gymnasium expects the user to call reset(), which is a
        # no-op duplicate here and keeps both conventions correct.
        return self.c.obs.copy(), reward, terminated, False, self._info()

    def _info(self) -> dict[str, Any]:
        c = self.c
        return {
            "x": c.x, "y": c.y, "vspeed": c.vspeed, "hspeed": c.hspeed,
            "on_ground": c.on_ground, "djump": c.djump, "tick": c.tick,
            "goal": c.goal, "last_event": c.last_event,
            "is_success": c.last_event == 2,
            "deaths": c.deaths,
            "room": c.room,
            "room_transitions": c.room_transitions,
        }

    def render(self):
        if self.c is None:
            return None
        if self._base_img is None:
            self._base_img = render_tiles(self.c.tiles())
        return render_frame(self._base_img, self.c.x, self.c.y, goal=self.c.goal,
                            entities=self.c.entities())

    def close(self):
        if self.c is not None:
            self.c.close()
            self.c = None


class IWannaGoalEnv(IWannaEnv):
    """Goal-conditioned variant: dict observations + HER compute_reward.

    achieved_goal / desired_goal are (x, y) positions normalized to [-1, 1]
    by room half-extents. Set random_goal=True to resample a reachable goal
    tile each episode (goal-conditioned training); the desired goal can also
    be overridden per-episode via reset(options={"goal": (px, py)}) in room
    pixels.
    """

    def __init__(self, level: str = "gaps", sparse: bool = True, **kw):
        kw.setdefault("random_goal", True)
        kw["reward_mode"] = "sparse" if sparse else "dense"
        super().__init__(level=level, **kw)
        base = self.observation_space
        goal_box = spaces.Box(-1.0, 1.0, (2,), np.float32)
        self.observation_space = spaces.Dict(
            observation=base, achieved_goal=goal_box, desired_goal=goal_box
        )

    def _norm_xy(self, x: float, y: float) -> np.ndarray:
        W, H = self.c.tw * TILE, self.c.th * TILE
        return np.array([2 * x / W - 1, 2 * y / H - 1], np.float32)

    def _dict_obs(self) -> dict[str, np.ndarray]:
        gx, gy = self.c.goal
        return {
            "observation": self.c.obs.copy(),
            "achieved_goal": self._norm_xy(self.c.x, self.c.y),
            "desired_goal": self._norm_xy(gx, gy),
        }

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        _, info = super().reset(seed=seed)
        if options and "goal" in options:
            gx, gy = options["goal"]
            self.c.set_goal(float(gx), float(gy))
        return self._dict_obs(), info

    def step(self, action: int):
        _, reward, terminated, truncated, info = super().step(action)
        return self._dict_obs(), reward, terminated, truncated, info

    def compute_reward(self, achieved_goal, desired_goal, info=None):
        """Vectorized HER reward: 1.0 within goal-overlap reach, else 0.0."""
        a = np.asarray(achieved_goal, np.float32)
        d = np.asarray(desired_goal, np.float32)
        W, H = self.c.tw * TILE, self.c.th * TILE
        dx = np.abs(a[..., 0] - d[..., 0]) * (W / 2)
        dy = np.abs(a[..., 1] - d[..., 1]) * (H / 2)
        return ((dx <= GOAL_REACH_X) & (dy <= GOAL_REACH_Y)).astype(np.float32)


class PixelObsWrapper(gym.ObservationWrapper):
    """RGB pixel observations. factor=8 -> 100x76x3 for an 800x608 room."""

    def __init__(self, env: IWannaEnv, factor: int = 8):
        super().__init__(env)
        self.factor = factor
        e: IWannaEnv = env.unwrapped
        text = e.level_text
        rows = [r for r in text.splitlines()
                if r.strip() and not r.lstrip().startswith("@")]
        h, w = len(rows) * TILE, max(len(r) for r in rows) * TILE
        self.observation_space = spaces.Box(
            0, 255, (h // factor, w // factor, 3), np.uint8
        )

    def observation(self, observation):
        e: IWannaEnv = self.env.unwrapped
        if e._base_img is None:
            e._base_img = render_tiles(e.c.tiles())
        img = render_frame(e._base_img, e.c.x, e.c.y, goal=e.c.goal,
                           entities=e.c.entities())
        return downsample(img, self.factor)
