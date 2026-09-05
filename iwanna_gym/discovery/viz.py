"""Unified visualization for every discovery task type.

One entry point renders classic/controlled text rooms AND source-native
exact-game rooms (camera view, player, entities — reusing the pack
renderer behind the README GIFs), and one entry point records an
annotated evaluation rollout (task id, attempt counter, death/success
flashes) as a GIF from a deterministic (task_seed, actions) replay or a
live policy. Rendering never runs during training — recording replays
actions offline, exactly as the systems contract requires.

By default pack rendering hides entities the source would not draw
(`visible_only=True`, via the drawn-status introspection), so the video
shows what an agent under the observable profile could actually see;
`visible_only=False` is the debug view.
"""
from __future__ import annotations

import importlib.util
import os

import numpy as np

from iwanna_gym.render import downsample, render_frame, render_tiles

from . import registry as R

VIEW_W, VIEW_H = 800, 608


def _pack_renderer():
    p = os.path.join("scripts", "record_room_gif.py")
    spec = importlib.util.spec_from_file_location("iw_pack_gif", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ #
# tiny 3x5 bitmap font for annotations (digits, caps, punctuation)
# ------------------------------------------------------------------ #

_FONT = {
    "0": "111101101101111", "1": "010110010010111",
    "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111",
    "6": "111100111101111", "7": "111001010010010",
    "8": "111101111101111", "9": "111101111001111",
    "A": "010101111101101", "B": "110101110101110",
    "C": "011100100100011", "D": "110101101101110",
    "E": "111100110100111", "F": "111100110100100",
    "G": "011100101101011", "H": "101101111101101",
    "I": "111010010010111", "K": "101110100110101",
    "L": "100100100100111", "M": "101111111101101",
    "N": "101111111111101", "O": "010101101101010",
    "P": "110101110100100", "R": "110101110110101",
    "S": "011100010001110", "T": "111010010010010",
    "U": "101101101101111", "V": "101101101101010",
    "W": "101101111111101", "X": "101010010010101",
    "Y": "101101010010010", "Z": "111001010100111",
    ".": "000000000000010", ":": "000010000010000",
    "/": "001001010100100", "-": "000000111000000",
    " ": "000000000000000", "_": "000000000000111",
}


def draw_text(img: np.ndarray, x: int, y: int, text: str,
              color=(255, 255, 255), scale: int = 2) -> None:
    for ch in text.upper():
        bits = _FONT.get(ch, _FONT[" "])
        for i, b in enumerate(bits):
            if b == "1":
                r, c = divmod(i, 3)
                y0, x0 = y + r * scale, x + c * scale
                img[y0:y0 + scale, x0:x0 + scale] = color
        x += 4 * scale


def _annotate(frame: np.ndarray, task_id: str, attempt: int,
              deaths: int, flash: str | None) -> np.ndarray:
    img = frame.copy()
    bar_h = 18
    img[:bar_h] = (img[:bar_h] * 0.25).astype(np.uint8)
    short = task_id.split(".", 1)[-1][:44]
    draw_text(img, 4, 4, f"{short} A{attempt} D{deaths}")
    if flash == "death":
        img[:4] = (220, 60, 60)
        img[-4:] = (220, 60, 60)
        img[:, :4] = (220, 60, 60)
        img[:, -4:] = (220, 60, 60)
    elif flash == "success":
        img[:4] = (80, 220, 100)
        img[-4:] = (80, 220, 100)
        img[:, :4] = (80, 220, 100)
        img[:, -4:] = (80, 220, 100)
    return img


# ------------------------------------------------------------------ #
# unified frame rendering
# ------------------------------------------------------------------ #

class TaskRenderer:
    """Renders the current state of ANY discovery env (controlled text
    room or exact-game pack room) as an (H, W, 3) uint8 view frame."""

    def __init__(self, env, visible_only: bool = True):
        self.c = env.c if hasattr(env, "c") else env
        self.is_pack = bool(getattr(self.c, "num_rooms", 1) > 1
                            or self.c.exact)
        self.visible_only = visible_only
        self._mod = _pack_renderer() if self.is_pack else None
        self._base = None
        self._base_room = None

    def frame(self) -> np.ndarray:
        c = self.c
        if not self.is_pack:
            if self._base is None:
                self._base = render_tiles(c.tiles())
            return render_frame(self._base, c.x, c.y, goal=c.goal,
                                entities=c.entities())
        if self._base is None or self._base_room != c.room:
            self._base = self._mod.static_base(c)
            self._base_room = c.room
        room_w, room_h = c.room_px
        if not self.visible_only:
            return self._mod.render_frame(c, self._base, room_w, room_h)
        # visible-only: mask out entities the source would not draw
        drawn = c.xents_drawn()
        full = c.xents()
        keep = full[drawn[:len(full)] == 1] if len(full) else full
        return self._render_visible(keep, room_w, room_h)

    def _render_visible(self, keep, room_w, room_h):
        m = self._mod
        c = self.c
        img = self._base.copy()
        for row in keep:
            cls = int(row[0])
            if row[6] < 1:
                continue
            color = m.CLS_COLOR.get(cls, m.HAZARD)
            if color is None:
                continue
            w, h = m.SIZES.get(cls, (28, 28))
            x, y = float(row[1]), float(row[2])
            m.draw_rect(img, x - 2, y - 2, x + w - 2, y + h - 2, color)
        for row in c.entities(4096):
            t = int(row[0])
            x, y = float(row[1]), float(row[2])
            if t == 8:
                m.draw_rect(img, x - 14, y - 10, x + 14, y + 12, m.SAVE)
            elif t == 9:
                m.draw_rect(img, x - 12, y - 14, x + 12, y + 14, m.WARPC)
            elif t == 12:
                m.draw_rect(img, x - 5, y - 1, x + 5, y + 1, m.BULLET)
        l, t, r, b = c.hitbox
        m.draw_rect(img, c.x + l, c.y + t, c.x + r + 1, c.y + b + 1, m.KID)
        vx, vy = c.view
        vx = int(max(0, min(room_w - VIEW_W, vx)))
        vy = int(max(0, min(room_h - VIEW_H, vy)))
        return img[vy:vy + VIEW_H, vx:vx + VIEW_W]


def record_rollout(task_id: str, out_path: str,
                   actions=None, policy=None,
                   task_seed: int = 1, max_frames: int = 4000,
                   skip: int = 2, scale: float = 0.5,
                   obs_mode: str = "observable_vector",
                   visible_only: bool = True) -> dict:
    """Replay (task_seed, actions) — or drive `policy(obs)` — through a
    discovery task, rendering an annotated GIF: header bar with task id
    / attempt / death counters, red border flash on death, green on
    success. Returns a summary dict (frames, attempts, success)."""
    from PIL import Image
    env = R.make_env(task_id, obs_mode=obs_mode)
    obs, info = env.reset(seed=0, options={"task_seed": task_seed})
    rend = TaskRenderer(env, visible_only=visible_only)
    frames = []
    flash_left, flash_kind = 0, None
    acts = list(actions) if actions is not None else None
    deaths = 0
    t = 0
    success = False
    while t < max_frames:
        a = (acts.pop(0) if acts else
             (policy(obs) if policy else 2))
        if acts == []:
            acts = None
        obs, rwd, term, tr, info = env.step(int(a))
        t += 1
        if info["attempt_ended"]:
            if info.get("task_success"):
                flash_left, flash_kind = 14, "success"
                success = True
            else:
                deaths += (info["last_event"] == 1)
                flash_left, flash_kind = 10, "death"
        if t % skip == 0 or flash_left > 0:
            fr = _annotate(rend.frame(), task_id, info["attempt_id"],
                           deaths, flash_kind if flash_left else None)
            flash_left = max(0, flash_left - 1)
            im = Image.fromarray(fr)
            if scale != 1.0:
                im = im.resize((int(fr.shape[1] * scale),
                                int(fr.shape[0] * scale)), Image.NEAREST)
            frames.append(im)
        if term:
            break
    env.close()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   loop=0, duration=int(1000 / 25))
    return dict(task_id=task_id, out=out_path, video_frames=len(frames),
                env_frames=t, deaths=deaths, success=success)


__all__ = ["TaskRenderer", "record_rollout", "draw_text", "downsample"]
