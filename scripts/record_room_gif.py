"""Record showcase GIFs of the exact IWBTGR rooms (camera-view crops).

No trained agent required: drives the env with small scripted/random
policies and renders tiles + static colliders + exact-layer entities.

    python scripts/record_room_gif.py --room rGuy1 --out docs/iwbtgr_guy1.gif
    python scripts/record_room_gif.py --all      # the README set
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
from PIL import Image                                     # noqa: E402

from iwanna_gym.clib import CIWanna                       # noqa: E402
from iwanna_gym.games import iwbtgr_1_5_3 as G            # noqa: E402
from iwanna_gym.games.iwbtgr_1_5_3 import exact as X      # noqa: E402
from iwanna_gym.render import render_tiles                # noqa: E402

VIEW_W, VIEW_H = 800, 608

# class -> RGB (categories: hazards red, platforms tan, pickups gold,
# regions translucent-ish flat, enemies violet, walls yellow)
HAZARD = (226, 88, 88)
PLATFORM = (168, 124, 66)
ENEMY = (188, 92, 196)
PICKUP = (240, 208, 96)
WALL = (222, 202, 64)
WATER = (70, 130, 220)
SOLID = (96, 96, 128)
MARKER = None            # not drawn
KID = (235, 80, 80)
BULLET = (250, 250, 250)
SAVE = (90, 160, 220)
WARPC = (170, 120, 240)

CLS_COLOR = {}
for name, idx in X.C.items():
    if name in ("XB_MARKER", "XB_TRIGGER", "XB_QLTIMER", "XB_LOCKCONTROLS",
                "XB_WITCHSHADOW", "XB_CHEEPCTL", "XB_FACTORYCTL",
                "XB_REALYOKUCTL", "XB_TETRIS", "XB_WATCHFOR",
                "XB_METROIDTRAP", "XB_SPAGDISP", "XB_GHOULGEN",
                "XB_MEDUSAMAKER", "XB_KAMEK", "XB_SNIFITCANNON"):
        CLS_COLOR[idx] = None
    elif name in ("XB_MOVPLAT", "XB_FALLPLAT", "XB_METROIDPLAT", "XB_ASCENT",
                  "XB_KUMO", "XB_GUYPLAT", "XB_PILLAR", "XB_CART",
                  "XB_FACTORYBLOCK", "XB_REALYOKU", "XB_SPIKESHOOT"):
        CLS_COLOR[idx] = PLATFORM
    elif name in ("XB_WALLSTRIP",):
        CLS_COLOR[idx] = WALL
    elif name in ("XB_WATER",):
        CLS_COLOR[idx] = WATER
    elif name in ("XB_ORB", "XB_SECRET", "XB_ASCENTMOD", "XB_CARTPICKUP"):
        CLS_COLOR[idx] = PICKUP
    elif name in ("XB_TETBLOCK", "XB_CONDSOLID", "XB_TOURIANBARRIER",
                  "XB_DESTRUCTIBLE", "XB_SHOOTBARRIER", "XB_NATSCAT",
                  "XB_HILL", "XB_SPINNER", "XB_FRBARRIER"):
        CLS_COLOR[idx] = SOLID
    elif name in ("XB_MEDUSA", "XB_BIRD", "XB_GHOUL", "XB_HOVERGUNNER",
                  "XB_SNIPER", "XB_TOURTURRET", "XB_SKWEE", "XB_CRAWLER",
                  "XB_DUMBBUGZ", "XB_METROID", "XB_PLAYSTATION", "XB_CHEEP",
                  "XB_BULLETBILL", "XB_WITCH", "XB_LONK", "XB_SPIKEMAN"):
        CLS_COLOR[idx] = ENEMY
    else:
        CLS_COLOR[idx] = HAZARD

SIZES = {X.C["XB_CART"]: (106, 40), X.C["XB_LONK"]: (75, 80),
         X.C["XB_KILLPILL"]: (300, 160), X.C["XB_MOONBIG"]: (240, 240)}


def draw_rect(img, x0, y0, x1, y1, color):
    h, w, _ = img.shape
    x0, x1 = int(max(0, x0)), int(min(w, x1))
    y0, y1 = int(max(0, y0)), int(min(h, y1))
    if x1 > x0 and y1 > y0:
        img[y0:y1, x0:x1] = color


def render_frame(c, base, room_w, room_h):
    img = base.copy()
    # exact entities
    for row in c.xents():
        cls = int(row[0])
        if row[6] < 1:
            continue
        color = CLS_COLOR.get(cls, HAZARD)
        if color is None:
            continue
        w, h = SIZES.get(cls, (28, 28))
        x, y = float(row[1]), float(row[2])
        draw_rect(img, x - 2, y - 2, x + w - 2, y + h - 2, color)
    # legacy entities (saves, warps, player bullets)
    for row in c.entities(4096):
        t = int(row[0])
        x, y = float(row[1]), float(row[2])
        if t == 8:
            draw_rect(img, x - 14, y - 10, x + 14, y + 12, SAVE)
        elif t == 9:
            draw_rect(img, x - 12, y - 14, x + 12, y + 14, WARPC)
        elif t == 12:
            draw_rect(img, x - 5, y - 1, x + 5, y + 1, BULLET)
    # the Kid
    l, t, r, b = c.hitbox
    draw_rect(img, c.x + l, c.y + t, c.x + r + 1, c.y + b + 1, KID)
    draw_rect(img, c.x + l, c.y + t, c.x + r + 1, c.y + t + 6, (40, 40, 45))
    # camera crop
    vx, vy = c.view
    vx = int(max(0, min(room_w - VIEW_W, vx)))
    vy = int(max(0, min(room_h - VIEW_H, vy)))
    return img[vy:vy + VIEW_H, vx:vx + VIEW_W]


def static_base(c):
    tiles = c.tiles()
    img = render_tiles(tiles).copy()
    for s in c.solids():
        draw_rect(img, s[0], s[1], s[2] + 1, s[3] + 1, SOLID)
    for k in c.killers():
        draw_rect(img, k[1], k[2], k[3] + 1, k[4] + 1, (205, 205, 215))
    return img


def record(room, out, policy="mixed", frames=700, skip=2, scale=0.5,
           seed=11, start_actions=None):
    c = CIWanna.from_pack(G.load_pack(), seed=seed, checkpoint_respawn=True,
                          start_room=G.room_names().index(room))
    c.reset()
    base = static_base(c)
    room_w, room_h = c.room_px
    imgs = []
    script = list(start_actions or [])
    rng = np.random.RandomState(seed)
    last_room = c.room
    for t in range(frames):
        if script:
            a = script.pop(0)
        elif policy == "right":
            a = 5 if t % 31 < 7 else 4
        elif policy == "idle":
            a = 2
        else:
            a = int(rng.randint(0, 12))
        c.step(a)
        if c.room != last_room:      # keep single-room showcases stable
            break
        if t % skip == 0:
            fr = render_frame(c, base, room_w, room_h)
            im = Image.fromarray(fr)
            if scale != 1.0:
                im = im.resize((int(VIEW_W * scale), int(VIEW_H * scale)),
                               Image.NEAREST)
            imgs.append(im)
    c.close()
    imgs[0].save(out, save_all=True, append_images=imgs[1:], loop=0,
                 duration=int(1000 / 25))
    print(f"wrote {out} ({len(imgs)} frames)")


README_SET = [
    ("rGuy1", "docs/iwbtgr_rguy1.gif", "mixed", 600, dict(seed=6)),
    ("rGuyFortress1", "docs/iwbtgr_fortress_fire.gif", "right", 500,
     dict(seed=3)),
    ("rKraidgiefLair", "docs/iwbtgr_tetris.gif", "idle", 700,
     dict(seed=1)),
    ("rGuyRoad", "docs/iwbtgr_cart.gif", "idle", 500, dict(seed=2)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room")
    ap.add_argument("--out")
    ap.add_argument("--policy", default="mixed")
    ap.add_argument("--frames", type=int, default=700)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.all:
        for room, out, pol, fr, kw in README_SET:
            record(room, out, policy=pol, frames=fr, **kw)
        return 0
    record(args.room, args.out, policy=args.policy, frames=args.frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
