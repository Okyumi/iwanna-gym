"""Numpy RGB renderer (no external deps). 32 px tiles, full room = 800x608."""
from __future__ import annotations

import numpy as np

TILE = 32
# tile codes (must match iwanna.h)
T_EMPTY, T_BLOCK, T_SPIKE_UP, T_SPIKE_DOWN, T_SPIKE_LEFT, T_SPIKE_RIGHT, T_GOAL = range(7)

BG = np.array([12, 12, 20], np.uint8)
BLOCK = np.array([60, 60, 80], np.uint8)
BLOCK_EDGE = np.array([90, 90, 120], np.uint8)
SPIKE = np.array([200, 200, 210], np.uint8)
GOAL = np.array([80, 220, 120], np.uint8)
KID = np.array([235, 80, 80], np.uint8)
KID_HEAD = np.array([40, 40, 45], np.uint8)

# hitbox offsets relative to origin (must match iwanna.h)
HB_L, HB_R, HB_T, HB_B = -5, 5, -11, 8

_iy, _ix = np.mgrid[0:TILE, 0:TILE]
_MASKS = {
    T_SPIKE_UP: np.abs(_ix - 15.5) <= (_iy + 1) * 0.5,
    T_SPIKE_DOWN: np.abs(_ix - 15.5) <= (TILE - _iy) * 0.5,
    T_SPIKE_LEFT: np.abs(_iy - 15.5) <= (_ix + 1) * 0.5,
    T_SPIKE_RIGHT: np.abs(_iy - 15.5) <= (TILE - _ix) * 0.5,
}


def render_tiles(tiles: np.ndarray) -> np.ndarray:
    """Render the static level once. tiles: (th, tw) uint8 -> (th*32, tw*32, 3)."""
    th, tw = tiles.shape
    img = np.empty((th * TILE, tw * TILE, 3), np.uint8)
    img[:] = BG
    for ty in range(th):
        for tx in range(tw):
            t = tiles[ty, tx]
            if t == T_EMPTY:
                continue
            y0, x0 = ty * TILE, tx * TILE
            cell = img[y0:y0 + TILE, x0:x0 + TILE]
            if t == T_BLOCK:
                cell[:] = BLOCK
                cell[0, :] = BLOCK_EDGE
                cell[-1, :] = BLOCK_EDGE
                cell[:, 0] = BLOCK_EDGE
                cell[:, -1] = BLOCK_EDGE
            elif t == T_GOAL:
                cell[4:-4, 4:-4] = GOAL
            elif t in _MASKS:
                cell[_MASKS[t]] = SPIKE
    return img


def render_frame(
    base: np.ndarray,
    x: float,
    y: float,
    goal: tuple[float, float] | None = None,
) -> np.ndarray:
    """Composite the player (and optional goal marker) onto a copy of base."""
    img = base.copy()
    H, W, _ = img.shape
    if goal is not None:
        gx, gy = int(goal[0]), int(goal[1])
        x0, x1 = max(gx - 16, 0), min(gx + 16, W)
        y0, y1 = max(gy - 16, 0), min(gy + 16, H)
        if x1 > x0 and y1 > y0:
            img[y0:y1, x0, :] = GOAL
            img[y0:y1, x1 - 1, :] = GOAL
            img[y0, x0:x1, :] = GOAL
            img[y1 - 1, x0:x1, :] = GOAL
    ix, iy = int(round(x)), int(round(y))
    x0, x1 = max(ix + HB_L, 0), min(ix + HB_R + 1, W)
    y0, y1 = max(iy + HB_T, 0), min(iy + HB_B + 1, H)
    if x1 > x0 and y1 > y0:
        img[y0:y1, x0:x1] = KID
        img[y0:min(y0 + 6, y1), x0:x1] = KID_HEAD
    return img


def downsample(img: np.ndarray, factor: int = 8) -> np.ndarray:
    """Cheap box downsample: (H, W, 3) -> (H//f, W//f, 3)."""
    H, W, C = img.shape
    H2, W2 = H - H % factor, W - W % factor
    v = img[:H2, :W2].reshape(H2 // factor, factor, W2 // factor, factor, C)
    return v.mean(axis=(1, 3)).astype(np.uint8)
