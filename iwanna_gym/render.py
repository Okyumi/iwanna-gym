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

# entity types + half-extents (must match iwanna.h)
(E_NONE, E_PLATFORM, E_SPIKEBALL, E_TRIGGER, E_TRAP, E_PROJECTILE,
 E_SHOOTER, E_ENEMY, E_SAVE, E_WARP, E_BOSS, E_GATE) = range(12)
ENT_HW = [0, 16, 10, 0, 16, 4, 12, 11, 14, 14, 16, 16]
ENT_HH = [0, 8, 10, 0, 16, 4, 12, 14, 14, 14, 16, 16]

PLATFORM_C = np.array([150, 110, 60], np.uint8)
# Anti-leakage fix L2 (docs/discovery_benchmark_contract.md section 7):
# a dormant trap spike must be INDISTINGUISHABLE from a static spike —
# that is the fangame trick. Both trap states therefore draw in the
# static SPIKE color; the old dormant/live color split leaked dormancy.
TRAP_DORMANT = SPIKE
TRAP_LIVE = SPIKE
HAZARD = np.array([230, 120, 120], np.uint8)
ENEMY_C = np.array([190, 80, 190], np.uint8)
SAVE_C = np.array([90, 160, 220], np.uint8)
SAVE_USED = np.array([120, 220, 120], np.uint8)
WARP_C = np.array([170, 120, 240], np.uint8)
GATE_C = np.array([120, 96, 70], np.uint8)
GATE_OPEN = np.array([80, 76, 90], np.uint8)

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


def _blit_rect(img: np.ndarray, cx: float, cy: float, hw: int, hh: int,
               color: np.ndarray, outline: bool = False) -> None:
    H, W, _ = img.shape
    x0, x1 = max(int(cx) - hw, 0), min(int(cx) + hw, W)
    y0, y1 = max(int(cy) - hh, 0), min(int(cy) + hh, H)
    if x1 <= x0 or y1 <= y0:
        return
    if outline:
        img[y0:y1, x0, :] = color
        img[y0:y1, x1 - 1, :] = color
        img[y0, x0:x1, :] = color
        img[y1 - 1, x0:x1, :] = color
    else:
        img[y0:y1, x0:x1] = color


def _draw_entities(img: np.ndarray, entities: np.ndarray) -> None:
    """entities: (N, 8) rows [type, x, y, vx, vy, state, dormant, p4]."""
    H, W, _ = img.shape
    for row in entities:
        t = int(row[0])
        ex, ey = row[1], row[2]
        if t in (E_NONE, E_TRIGGER):        # triggers are invisible
            continue
        if t >= len(ENT_HW):
            continue
        hw, hh = int(ENT_HW[t]), int(ENT_HH[t])
        if t == E_PLATFORM:
            _blit_rect(img, ex, ey, hw, hh, PLATFORM_C)
        elif t == E_TRAP:
            d = int(row[7])
            mask_t = (T_SPIKE_UP, T_SPIKE_DOWN, T_SPIKE_LEFT, T_SPIKE_RIGHT)[d % 4]
            c = TRAP_DORMANT if row[6] > 0 else TRAP_LIVE
            x0, y0 = int(ex) - 16, int(ey) - 16
            if 0 <= x0 and x0 + TILE <= W and 0 <= y0 and y0 + TILE <= H:
                cell = img[y0:y0 + TILE, x0:x0 + TILE]
                cell[_MASKS[mask_t]] = c
        elif t in (E_SPIKEBALL, E_PROJECTILE):
            _blit_rect(img, ex, ey, hw, hh, HAZARD)
        elif t in (E_ENEMY, E_BOSS, E_SHOOTER):
            _blit_rect(img, ex, ey, hw, hh, ENEMY_C)
        elif t == E_SAVE:
            _blit_rect(img, ex, ey, hw, hh, SAVE_USED if row[5] > 0 else SAVE_C)
        elif t == E_WARP:
            _blit_rect(img, ex, ey, hw, hh, WARP_C, outline=True)
        elif t == E_GATE:
            # p4 packs the size: w*100 + h (tiles)
            p4 = int(row[7])
            gw, gh = max(p4 // 100, 1), max(p4 % 100, 1)
            ghw, ghh = gw * TILE // 2, gh * TILE // 2
            if row[5] > 0:                      # closed: solid door
                _blit_rect(img, ex, ey, ghw, ghh, GATE_C)
                _blit_rect(img, ex, ey, ghw, ghh, np.array([60, 48, 35], np.uint8),
                           outline=True)
            else:                               # open: faint frame
                _blit_rect(img, ex, ey, ghw, ghh, GATE_OPEN, outline=True)


def render_frame(
    base: np.ndarray,
    x: float,
    y: float,
    goal: tuple[float, float] | None = None,
    entities: np.ndarray | None = None,
) -> np.ndarray:
    """Composite entities, the player, and the goal marker onto a copy of base."""
    img = base.copy()
    H, W, _ = img.shape
    if entities is not None and len(entities):
        _draw_entities(img, entities)
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
