"""Native vectorized stepping for heterogeneous discovery tasks.

One shared (N, OBS) observation block, one C call per frame
(``iw_vec_step``), zero Python callbacks and zero allocation in the
frame loop — the same core path the PufferLib binding drives, usable
directly for training and benchmarking. Every task class loads through
the same interface: controlled research rooms, accepted
``iwbtgr_1_5_3`` exact-game tasks, and any future coverage-approved
pack (``k2warped_gms14`` OOD tasks, ``iwbtg_original_2007``) the moment
its pack exists — an entry may also name a raw ``.iwpack`` path
directly, so no new environment code is ever needed for a new game.

Boundary flags (``attempt_ended`` / ``task_ended`` / ``task_success``)
are written by C into caller-owned uint8 vectors on every step so a
recurrent trainer can carry state across attempt deaths and cut it at
task boundaries with pure array ops.

Deterministic seeding: env i's task seed is
``base_seed * 1_000_003 + i * 7_919`` (and each env's RNG stream is
re-fixed per task by the core), so a (config, base_seed) pair
reproduces the whole batch bit-for-bit.
"""
from __future__ import annotations

import ctypes
from typing import Any

import numpy as np

from iwanna_gym.clib import LIB, OBS_SIZE, CIWanna

from . import registry as R


def _entry_spec(entry: Any, reg) -> dict:
    """Normalize a vector entry to construction parameters."""
    if isinstance(entry, str):
        spec = reg[entry]
        kw: dict[str, Any] = dict(
            task_id=spec.task_id,
            K=spec.attempts_K, H=spec.attempt_frames_H,
            action_n=12 if spec.suite == "iwbtg_native" else 6)
        if spec.suite == "iwbtg_native":
            from iwanna_gym.games import get_game
            import os
            gmod = get_game(spec.game)
            kw["pack_path"] = (os.environ.get("IWANNA_IWBTGR_PACK")
                               or gmod.PACK_PATH)
            kw["start_room"] = gmod.room_index(spec.room)
            kw["start_xy"] = spec.start_xy
            kw["goal_rect"] = spec.goal_rect
        else:
            from iwanna_gym.levels import load_level
            kw["level_text"] = load_level(spec.room)
        return kw
    if isinstance(entry, dict):
        e = dict(entry)
        e.setdefault("task_id", e.get("level") or e.get("pack_path"))
        e.setdefault("K", 25)
        e.setdefault("H", 2000)
        e.setdefault("action_n", 12 if "pack_path" in e else 6)
        if "level" in e:
            from iwanna_gym.levels import load_level
            lvl = e.pop("level")
            # accept inline level text (contains newlines) or a name/path
            e["level_text"] = lvl if "\n" in lvl else load_level(lvl)
        return e
    raise TypeError(f"bad vector entry {entry!r}")


class CVecIWanna:
    """N independent native envs stepped by one C call per frame."""

    def __init__(self, entries: list[Any],
                 obs_mode: str = "observable_vector",
                 base_seed: int = 1,
                 registry: dict | None = None):
        if obs_mode not in ("observable_vector", "privileged_vector"):
            raise ValueError(f"vector path supports vector obs modes, "
                             f"not {obs_mode!r}")
        reg = registry if registry is not None else R.load_registry()
        n = len(entries)
        self.n = n
        self.obs_mode = obs_mode
        self.obs = np.zeros((n, OBS_SIZE), np.float32)
        self.act = np.zeros((n, 1), np.int32)
        self.rew = np.zeros((n, 1), np.float32)
        self.term = np.zeros((n, 1), np.uint8)
        self.attempt_ended = np.zeros(n, np.uint8)
        self.task_ended = np.zeros(n, np.uint8)
        self.task_success = np.zeros(n, np.uint8)
        # per-env terminal-event code: 0 none 1 death 2 success
        # 3 timeout 4 game complete (written by iw_vec_step_ev)
        self.attempt_event = np.zeros(n, np.uint8)
        om = 0 if obs_mode == "privileged_vector" else 1

        pack_cache: dict[str, bytes] = {}
        self.envs: list[CIWanna] = []
        self.task_ids: list[str] = []
        self.action_n = 6
        for i, entry in enumerate(entries):
            e = _entry_spec(entry, reg)
            self.task_ids.append(str(e["task_id"]))
            self.action_n = max(self.action_n, e["action_n"])
            bufs = (self.obs[i], self.act[i], self.rew[i], self.term[i])
            seed = base_seed * 1_000_003 + i * 104_729 + 1
            if "pack_path" in e:
                p = e["pack_path"]
                if p not in pack_cache:
                    with open(p, "rb") as f:
                        pack_cache[p] = f.read()
                c = CIWanna(None, pack_data=pack_cache[p], buffers=bufs,
                            max_steps=e["K"] * e["H"], reward_mode=0,
                            death_penalty=1.0, seed=seed,
                            checkpoint_respawn=True)
                if e.get("start_room") is not None and \
                        e.get("start_xy") is None:
                    LIB.iw_set_start_room(c._h, int(e["start_room"]))
                if e.get("start_xy") is not None:
                    c.set_task_start(int(e["start_room"]), *e["start_xy"])
                if e.get("goal_rect") is not None:
                    c.set_task_goal(int(e["start_room"]), *e["goal_rect"])
                if e.get("difficulty"):
                    LIB.iw_set_difficulty(c._h, int(e["difficulty"]))
            else:
                c = CIWanna(e["level_text"], buffers=bufs,
                            max_steps=e["K"] * e["H"], reward_mode=0,
                            death_penalty=1.0, seed=seed)
            c.set_discovery(e["K"], e["H"], om)
            c.set_task_seed(base_seed * 1_000_003 + i * 7_919)
            self.envs.append(c)
        self._handles = (ctypes.c_void_p * n)(
            *[c._h for c in self.envs])

    def reset(self) -> np.ndarray:
        LIB.iw_vec_reset(self._handles, self.n)
        self.attempt_ended[:] = 0
        self.task_ended[:] = 0
        self.task_success[:] = 0
        self.attempt_event[:] = 0
        return self.obs

    def step(self, actions: np.ndarray):
        """One frame for the whole batch: exactly one C call. Returns
        (obs, rewards, task_terminals, attempt_ended, task_ended,
        task_success) — obs/rew/term are views into the shared block.
        self.attempt_event carries the per-env terminal-event code."""
        self.act[:, 0] = actions
        LIB.iw_vec_step_ev(self._handles, self.n,
                           self.attempt_ended, self.task_ended,
                           self.task_success, self.attempt_event)
        return (self.obs, self.rew[:, 0], self.term[:, 0],
                self.attempt_ended, self.task_ended, self.task_success)

    def bench(self, steps_per_env: int, seed: int = 7) -> float:
        """Pure-C random-action benchmark; returns seconds for
        steps_per_env * n total env frames."""
        return float(LIB.iw_vec_bench(self._handles, self.n,
                                      steps_per_env, seed, self.action_n))

    def set_task_seeds(self, seeds) -> None:
        for c, s in zip(self.envs, seeds):
            c.set_task_seed(int(s))

    def close(self) -> None:
        for c in self.envs:
            c.close()
        self.envs = []
