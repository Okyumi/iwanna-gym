"""ctypes loader for the IWanna C core (libiwanna.so)."""
from __future__ import annotations

import ctypes
import os
import subprocess

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_C_SRC = os.path.join(os.path.dirname(_HERE), "c_src")
_LIB_PATH = os.path.join(_C_SRC, "libiwanna.so")


def _build_lib() -> None:
    cmd = [
        "gcc", "-O2", "-fPIC", "-shared", "-DIW_NO_RAYLIB",
        "-o", _LIB_PATH, os.path.join(_C_SRC, "iwanna_capi.c"), "-lm",
    ]
    subprocess.run(cmd, check=True, cwd=_C_SRC)


def _load() -> ctypes.CDLL:
    if not os.path.exists(_LIB_PATH):
        _build_lib()
    lib = ctypes.CDLL(_LIB_PATH)
    f32p = np.ctypeslib.ndpointer(np.float32, flags="C_CONTIGUOUS")
    i32p = np.ctypeslib.ndpointer(np.int32, flags="C_CONTIGUOUS")
    u8p = np.ctypeslib.ndpointer(np.uint8, flags="C_CONTIGUOUS")

    lib.iw_new.restype = ctypes.c_void_p
    lib.iw_new.argtypes = [
        ctypes.c_char_p, f32p, i32p, f32p, u8p,
        ctypes.c_int, ctypes.c_int, ctypes.c_float,
        ctypes.c_int, ctypes.c_ulonglong, ctypes.c_int,
    ]
    lib.iw_new_pack.restype = ctypes.c_void_p
    lib.iw_new_pack.argtypes = [
        ctypes.c_char_p, ctypes.c_long, f32p, i32p, f32p, u8p,
        ctypes.c_int, ctypes.c_int, ctypes.c_float,
        ctypes.c_int, ctypes.c_ulonglong, ctypes.c_int,
    ]
    lib.iw_last_error.restype = ctypes.c_char_p
    lib.iw_last_error.argtypes = []
    lib.iw_delete.argtypes = [ctypes.c_void_p]
    lib.iw_reset.argtypes = [ctypes.c_void_p]
    lib.iw_step.argtypes = [ctypes.c_void_p]
    for name in ("iw_x", "iw_y", "iw_vspeed", "iw_hspeed", "iw_goal_x", "iw_goal_y"):
        fn = getattr(lib, name)
        fn.restype = ctypes.c_double
        fn.argtypes = [ctypes.c_void_p]
    for name in ("iw_djump", "iw_on_ground", "iw_tick", "iw_tw", "iw_th",
                  "iw_last_event", "iw_ent_count", "iw_deaths",
                  "iw_room", "iw_respawn_room", "iw_room_transitions",
                  "iw_num_rooms"):
        fn = getattr(lib, name)
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_void_p]
    for name in ("iw_respawn_x", "iw_respawn_y"):
        fn = getattr(lib, name)
        fn.restype = ctypes.c_double
        fn.argtypes = [ctypes.c_void_p]
    lib.iw_gflags.restype = ctypes.c_ulonglong
    lib.iw_gflags.argtypes = [ctypes.c_void_p]
    lib.iw_bench.restype = ctypes.c_double
    lib.iw_bench.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_ulonglong]
    lib.iw_entities.restype = ctypes.c_int
    lib.iw_entities.argtypes = [ctypes.c_void_p, f32p, ctypes.c_int]
    lib.iw_set_goal.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double]
    lib.iw_tiles.argtypes = [ctypes.c_void_p, u8p]
    lib.iw_set_state.argtypes = [
        ctypes.c_void_p, ctypes.c_double, ctypes.c_double,
        ctypes.c_double, ctypes.c_double, ctypes.c_int,
    ]
    lib.iw_obs_size.restype = ctypes.c_int
    lib.iw_num_actions.restype = ctypes.c_int
    lib.iw_num_levels.restype = ctypes.c_int
    lib.iw_level_text.restype = ctypes.c_char_p
    lib.iw_level_text.argtypes = [ctypes.c_int]
    return lib


LIB = _load()
OBS_SIZE: int = LIB.iw_obs_size()
NUM_ACTIONS: int = LIB.iw_num_actions()
NUM_BUILTIN_LEVELS: int = LIB.iw_num_levels()


def builtin_level_text(idx: int) -> str:
    return LIB.iw_level_text(idx).decode()


class CIWanna:
    """Thin handle over one C env instance sharing numpy buffers."""

    def __init__(
        self,
        level_text: str | None,
        max_steps: int = 1500,
        reward_mode: int = 1,
        death_penalty: float = 1.0,
        random_goal: bool = False,
        seed: int = 0,
        checkpoint_respawn: bool = False,
        pack_data: bytes | None = None,
    ):
        self.obs = np.zeros(OBS_SIZE, dtype=np.float32)
        self.act = np.zeros(1, dtype=np.int32)
        self.rew = np.zeros(1, dtype=np.float32)
        self.term = np.zeros(1, dtype=np.uint8)
        if pack_data is not None:
            self._h = LIB.iw_new_pack(
                pack_data, len(pack_data),
                self.obs, self.act, self.rew, self.term,
                max_steps, reward_mode, float(death_penalty),
                int(random_goal), seed, int(checkpoint_respawn),
            )
            if not self._h:
                raise ValueError(
                    "failed to load game pack: "
                    + LIB.iw_last_error().decode(errors="replace")
                )
        else:
            self._h = LIB.iw_new(
                level_text.encode(), self.obs, self.act, self.rew, self.term,
                max_steps, reward_mode, float(death_penalty),
                int(random_goal), seed, int(checkpoint_respawn),
            )
            if not self._h:
                raise ValueError("failed to parse level text")
        self.tw: int = LIB.iw_tw(self._h)
        self.th: int = LIB.iw_th(self._h)

    @classmethod
    def from_pack(cls, pack: bytes | str, **kw) -> "CIWanna":
        """Construct from a compiled .iwpack (bytes or file path)."""
        if isinstance(pack, str):
            with open(pack, "rb") as f:
                pack = f.read()
        return cls(None, pack_data=pack, **kw)

    def reset(self) -> None:
        LIB.iw_reset(self._h)

    def step(self, action: int) -> None:
        self.act[0] = action
        LIB.iw_step(self._h)

    # -- state accessors --
    @property
    def x(self) -> float: return LIB.iw_x(self._h)
    @property
    def y(self) -> float: return LIB.iw_y(self._h)
    @property
    def vspeed(self) -> float: return LIB.iw_vspeed(self._h)
    @property
    def hspeed(self) -> float: return LIB.iw_hspeed(self._h)
    @property
    def djump(self) -> int: return LIB.iw_djump(self._h)
    @property
    def on_ground(self) -> bool: return bool(LIB.iw_on_ground(self._h))
    @property
    def tick(self) -> int: return LIB.iw_tick(self._h)
    @property
    def goal(self) -> tuple[float, float]:
        return LIB.iw_goal_x(self._h), LIB.iw_goal_y(self._h)
    @property
    def last_event(self) -> int: return LIB.iw_last_event(self._h)
    @property
    def deaths(self) -> int: return LIB.iw_deaths(self._h)
    @property
    def ent_count(self) -> int: return LIB.iw_ent_count(self._h)
    @property
    def respawn(self) -> tuple[float, float]:
        return LIB.iw_respawn_x(self._h), LIB.iw_respawn_y(self._h)
    @property
    def room(self) -> int: return LIB.iw_room(self._h)
    @property
    def respawn_room(self) -> int: return LIB.iw_respawn_room(self._h)
    @property
    def room_transitions(self) -> int: return LIB.iw_room_transitions(self._h)
    @property
    def num_rooms(self) -> int: return LIB.iw_num_rooms(self._h)
    @property
    def gflags(self) -> int: return int(LIB.iw_gflags(self._h))

    def bench(self, steps: int, seed: int = 7) -> float:
        """Run `steps` random-action frames entirely in C; returns seconds."""
        return float(LIB.iw_bench(self._h, steps, seed))

    def entities(self, max_rows: int = 4096) -> np.ndarray:
        """Active entities as rows [type, x, y, vx, vy, state, dormant, p4]."""
        out = np.zeros((max_rows, 8), dtype=np.float32)
        n = LIB.iw_entities(self._h, out, max_rows)
        return out[:n]

    def set_goal(self, gx: float, gy: float) -> None:
        LIB.iw_set_goal(self._h, gx, gy)

    def set_state(self, x: float, y: float, hspeed: float = 0.0,
                  vspeed: float = 0.0, djump: int = 1) -> None:
        LIB.iw_set_state(self._h, x, y, hspeed, vspeed, djump)

    def tiles(self) -> np.ndarray:
        out = np.zeros(self.tw * self.th, dtype=np.uint8)
        LIB.iw_tiles(self._h, out)
        return out.reshape(self.th, self.tw)

    def close(self) -> None:
        if self._h:
            LIB.iw_delete(self._h)
            self._h = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
