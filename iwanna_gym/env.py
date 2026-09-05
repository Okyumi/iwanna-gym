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

from .clib import NUM_ACTIONS, NUM_ACTIONS_LEGACY, OBS_SIZE, CIWanna
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
        action_mode: str | None = None,
        save_mode: str | None = None,
    ):
        super().__init__()
        # Exact-game construction:
        #   IWannaEnv(game="iwbtgr_1_5_3", mode="full_game")
        #   IWannaEnv(game="iwbtgr_1_5_3", mode="room", room_id="rGuyLabyrinth")
        # `difficulty` gates difficulty-specific saves exactly as the source
        # does ("medium"/"hard"/"very_hard"/"impossible" or 0..3).
        self._start_room: int | None = None
        self._difficulty: int = 0
        self._game_id = game
        self._room_names: list[str] | None = None
        # action_mode: "legacy" = the original 6-action no-shoot space
        # (default for classic/research levels, keeping old experiments
        # unchanged); "full" = 12 actions with shoot (default for exact
        # games). Actions 0..5 mean the same thing in both.
        # save_mode: "shoot" = source-faithful shot-activated saves
        # (exact-game default); "touch" = legacy touch saves (research);
        # None = the mode's default.
        if action_mode not in (None, "legacy", "full"):
            raise ValueError(f"unknown action_mode {action_mode!r}")
        if save_mode not in (None, "shoot", "touch"):
            raise ValueError(f"unknown save_mode {save_mode!r}")
        self._save_mode = save_mode
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
            self._room_names = gmod.room_names()
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

        full = (action_mode == "full") or (action_mode is None and
                                           self._pack_data is not None)
        self.n_actions = NUM_ACTIONS if full else NUM_ACTIONS_LEGACY
        self.observation_space = spaces.Box(-1.0, 1.0, (OBS_SIZE,), np.float32)
        self.action_space = spaces.Discrete(self.n_actions)

    # -- gym api --
    def _ensure_c(self) -> bool:
        """Construct the C env on first use; returns True when created."""
        if self.c is not None:
            return False
        cseed = int(self.np_random.integers(1, 2**63 - 1))
        if self._pack_data is not None:
            self.c = CIWanna.from_pack(
                self._pack_data, seed=cseed,
                start_room=self._start_room,
                difficulty=self._difficulty, **self._cfg)
        else:
            self.c = CIWanna(self.level_text, seed=cseed, **self._cfg)
        if self._save_mode is not None:
            self.c.set_save_mode(self._save_mode == "shoot")
        return True

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self._ensure_c()
        self.c.reset()
        return self.c.obs.copy(), self._info()

    def attempt_reset(self):
        """ATTEMPT reset: same task, same active checkpoint — the source
        "R" quick-retry (pack mode: full room reset, exact saved
        position/facing restored, progression flags persist, no death
        counted). Use gym reset() for a TASK reset. Returns (obs, info)."""
        if self.c is None:
            return self.reset()
        self.c.attempt_reset()
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
        room = c.room
        room_name = (self._room_names[room]
                     if self._room_names and room < len(self._room_names)
                     else room)
        rx, ry = c.respawn
        return {
            "x": c.x, "y": c.y, "vspeed": c.vspeed, "hspeed": c.hspeed,
            "on_ground": c.on_ground, "djump": c.djump, "tick": c.tick,
            "goal": c.goal, "last_event": c.last_event,
            "is_success": c.last_event == 2,
            "deaths": c.deaths,
            "room": room,
            "room_transitions": c.room_transitions,
            # evaluation metadata (no hidden trap/world state is exposed)
            "game_id": self._game_id,
            "room_id": room_name,
            "checkpoint_id": f"{c.respawn_room}:{rx:.2f}:{ry:.2f}",
            "attempt_id": c.attempt,
            "death_count": c.deaths,
            "difficulty": c.difficulty,
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


class IWannaDiscoveryEnv(IWannaEnv):
    """Multi-attempt discovery task environment
    (docs/discovery_benchmark_contract.md section 1).

    One Gymnasium episode == one TASK. ``reset()`` is the TASK reset:
    it fixes the latent task identity (room content + task seed) and is
    where the agent must clear ALL cross-attempt memory. Death (or the
    per-attempt frame budget) ends an ATTEMPT: the C core restores the
    source-faithful checkpoint state, restores the task's random stream,
    and the episode CONTINUES — ``terminated`` stays False, so recurrent
    state naturally persists across attempts. The episode terminates
    only on success or an exhausted budget (``K`` attempts or
    ``max_steps`` total frames).

    All of that runs inside the shared native core (the same
    ``c_reset``/``c_step`` the PufferLib binding drives); this class is
    a thin Gymnasium reference interface over it.

    Observation modes:
      - ``observable_vector`` (default): the 101-dim vector restricted
        to information derivable from the visible scene + player
        proprioception (unmanifested/invisible entities excluded; the
        entity-type sign comes from appearance, never live deadliness).
      - ``privileged_vector``: the legacy simulator-truth vector —
        debugging/oracle only, FORBIDDEN for headline discovery runs.
      - ``pixels``: the source-faithful visible scene, rendered and
        downsampled (classic/research rooms; dormant traps draw
        identically to static spikes).

    The ``info`` dict fields (attempt_id, attempt_ended, task_ended,
    task_success, death_count, budgets, task_seed) are EVALUATOR-facing
    task-level logging; per the anti-leakage contract they must never be
    fed to the policy.

    Deterministic replay: ``reset(options={"task_seed": s})`` pins the
    task's random stream; (task_seed, action sequence) then reproduces
    the trajectory bit-for-bit, attempts included.
    """

    OBS_MODES = ("observable_vector", "privileged_vector", "pixels")

    def __init__(self, *, attempts_K: int = 25,
                 attempt_frames_H: int = 2000,
                 obs_mode: str = "observable_vector",
                 pixels_factor: int = 8,
                 max_steps: int | None = None,
                 task: str | None = None,
                 _task_spec=None, **kw):
        # registry-driven construction: IWannaDiscoveryEnv(task="disc….")
        if task is not None:
            from .discovery import load_registry, task_env_kwargs
            _task_spec = load_registry()[task]
            tk = task_env_kwargs(_task_spec)
            attempts_K = tk.pop("attempts_K")
            attempt_frames_H = tk.pop("attempt_frames_H")
            kw = {**tk, **kw}
        self._task_spec = _task_spec
        if obs_mode not in self.OBS_MODES:
            raise ValueError(f"unknown obs_mode {obs_mode!r}; "
                             f"choose from {self.OBS_MODES}")
        if max_steps is None:
            # total task frame budget defaults to the worst case
            max_steps = max(attempts_K, 1) * max(attempt_frames_H, 1)
        super().__init__(max_steps=max_steps, **kw)
        self.attempts_K = int(attempts_K)
        self.attempt_frames_H = int(attempt_frames_H)
        self.obs_mode = obs_mode
        self._pixels_factor = int(pixels_factor)
        if obs_mode == "pixels":
            if self._pack_data is not None:
                raise NotImplementedError(
                    "pixels obs for game packs needs the room renderer; "
                    "use observable_vector for pack tasks in this "
                    "milestone")
            rows = [r for r in self.level_text.splitlines()
                    if r.strip() and not r.lstrip().startswith(("@", "!"))]
            h = len(rows) * TILE // self._pixels_factor
            w = max(len(r) for r in rows) * TILE // self._pixels_factor
            self.observation_space = spaces.Box(0, 255, (h, w, 3), np.uint8)

    # C-side mode codes: 0 privileged, 1 observable (pixels renders the
    # visible scene; its vector buffer runs observable filtering too)
    def _c_obs_mode(self) -> int:
        return 0 if self.obs_mode == "privileged_vector" else 1

    def _obs(self):
        if self.obs_mode == "pixels":
            if self._base_img is None:
                self._base_img = render_tiles(self.c.tiles())
            img = render_frame(self._base_img, self.c.x, self.c.y,
                               goal=self.c.goal, entities=self.c.entities())
            return downsample(img, self._pixels_factor)
        return self.c.obs.copy()

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        gym.Env.reset(self, seed=seed)
        created = self._ensure_c()
        if created:
            self.c.set_discovery(self.attempts_K, self.attempt_frames_H,
                                 self._c_obs_mode())
            if self._task_spec is not None:
                from .discovery import apply_task_anchors
                apply_task_anchors(self.c, self._task_spec)
        if options and "task_seed" in options:
            self.c.set_task_seed(int(options["task_seed"]))
        self.c.reset()
        return self._obs(), self._info()

    def step(self, action: int):
        self.c.step(int(action))
        terminated = bool(self.c.term[0])
        return (self._obs(), float(self.c.rew[0]), terminated, False,
                self._info())

    def _info(self):
        info = super()._info()
        c = self.c
        info.update(
            attempt_ended=c.attempt_ended,
            task_ended=c.task_ended,
            task_success=c.task_success,
            attempts_K=self.attempts_K,
            attempt_frames_H=self.attempt_frames_H,
            attempt_tick=c.attempt_tick,
            task_seed=c.task_seed,
        )
        if c.task_ended:
            # the auto-reset already started the next task; these carry
            # the ENDED task's evaluation stats
            info.update(
                final_task_attempts=c.last_task_attempts,
                final_task_deaths=c.last_task_deaths,
                final_task_seed=c.last_task_seed,
            )
        return info


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
