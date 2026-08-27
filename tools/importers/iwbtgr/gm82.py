"""Reader for GameMaker 8.2 text-tree projects (the gm82save format).

The gm82save IDE mod (https://github.com/GM82Project/gm82save, pinned in
third_party/source_manifest.toml) stores a GM8.2 project as one text file
per resource, which makes extraction plain text parsing — no binary
reverse engineering. Field semantics below were verified against
gm82save's own writer (src/save.rs):

* ``rooms/<name>/instances.txt`` —
  ``object,x,y,id_hex,locked,xscale,yscale,blend,angle,has_code``;
  ``<id_hex>.gml`` holds that instance's creation code.
* ``rooms/<name>/<depth>.txt`` (depths listed in ``layers.txt``) —
  ``background,x,y,u,v,width,height,locked,xscale,yscale,blend`` per tile.
* ``rooms/<name>/room.txt`` — key=value settings (dims, speed, snap,
  8 background slots, 8 view slots); ``code.gml`` — room creation code.
* ``objects/<name>.txt`` — sprite/visible/solid/persistent/depth/parent/
  mask; ``objects/<name>.gml`` — events as ``#define <Event>_<n>``
  sections of GML (with YYD ACTION marker comments).
* ``sprites/<name>/sprite.txt`` + numbered frame PNGs; ``backgrounds/``
  likewise.
* ``rooms/tree.yyd`` etc. — resource-tree order (room order = game order).

This module is deliberately importer-agnostic: it reads any gm82save
project (renex² engine, IWBTGR, ...). Nothing here runs at RL training
time.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any

_EVENT_RE = re.compile(r"^#define\s+(\S+)\s*$", re.M)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def _kv(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in _read(path).splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _num(s: str) -> float | int | str:
    try:
        f = float(s)
        return int(f) if f == int(f) and "." not in s and "e" not in s.lower() else f
    except ValueError:
        return s


@dataclass
class Gm82Event:
    name: str                # e.g. Create_0, Step_1, Collision_block, Alarm_3
    code: str

    @property
    def lines(self) -> int:
        return len(self.code.splitlines())

    @property
    def sha256(self) -> str:
        return _sha256_text(self.code)


@dataclass
class Gm82Object:
    name: str
    sprite: str = ""
    visible: bool = True
    solid: bool = False
    persistent: bool = False
    depth: int = 0
    parent: str = ""
    mask: str = ""
    events: list[Gm82Event] = field(default_factory=list)

    def event(self, name: str) -> Gm82Event | None:
        for e in self.events:
            if e.name == name:
                return e
        return None


@dataclass
class Gm82Instance:
    object: str
    x: float
    y: float
    id_hex: str
    locked: int = 0
    xscale: float = 1.0
    yscale: float = 1.0
    blend: int = 4294967295
    angle: float = 0.0
    creation_code: str | None = None


@dataclass
class Gm82Tile:
    background: str
    x: float
    y: float
    u: float
    v: float
    width: float
    height: float
    depth: int
    xscale: float = 1.0
    yscale: float = 1.0
    blend: int = 4294967295


@dataclass
class Gm82Room:
    name: str
    settings: dict[str, Any] = field(default_factory=dict)
    width: int = 0
    height: int = 0
    speed: int = 0
    creation_code: str = ""
    backgrounds: list[dict[str, Any]] = field(default_factory=list)
    views: list[dict[str, Any]] = field(default_factory=list)
    instances: list[Gm82Instance] = field(default_factory=list)
    tiles: list[Gm82Tile] = field(default_factory=list)
    tile_layers: dict[int, int] = field(default_factory=dict)  # depth -> count


@dataclass
class Gm82Sprite:
    name: str
    props: dict[str, Any] = field(default_factory=dict)
    frame_count: int = 0
    frame_sha256: list[str] = field(default_factory=list)
    width: int | None = None
    height: int | None = None


@dataclass
class Gm82Project:
    root: str
    settings: dict[str, Any] = field(default_factory=dict)
    project_file: str = ""
    objects: dict[str, Gm82Object] = field(default_factory=dict)
    scripts: dict[str, str] = field(default_factory=dict)
    rooms: dict[str, Gm82Room] = field(default_factory=dict)
    room_order: list[str] = field(default_factory=list)
    sprites: dict[str, Gm82Sprite] = field(default_factory=dict)
    backgrounds: dict[str, Gm82Sprite] = field(default_factory=dict)
    triggers: dict[str, str] = field(default_factory=dict)
    paths: list[str] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    datafiles: list[str] = field(default_factory=list)

    # ---- derived ----
    def parent_chain(self, obj_name: str) -> list[str]:
        chain, seen = [], set()
        cur = self.objects.get(obj_name)
        while cur and cur.parent and cur.parent not in seen:
            seen.add(cur.parent)
            chain.append(cur.parent)
            cur = self.objects.get(cur.parent)
        return chain


def parse_events(gml_text: str) -> list[Gm82Event]:
    """Split an object .gml file into its ``#define`` event sections."""
    events: list[Gm82Event] = []
    matches = list(_EVENT_RE.finditer(gml_text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(gml_text)
        events.append(Gm82Event(m.group(1), gml_text[m.end():end].strip("\n")))
    return events


def _tree_order(path: str) -> list[str]:
    """Resource order from a tree.yyd (leaf lines start with '|')."""
    if not os.path.isfile(path):
        return []
    out = []
    for line in _read(path).splitlines():
        name = line.strip().lstrip("|+").strip()
        if name:
            out.append(name)
    return out


def is_gm82_project(root: str) -> bool:
    return any(fn.endswith(".gm82") for fn in os.listdir(root)) \
        if os.path.isdir(root) else False


def load_project(root: str, with_assets: bool = True) -> Gm82Project:
    proj = Gm82Project(root=root)
    gm82 = [fn for fn in os.listdir(root) if fn.endswith(".gm82")]
    if not gm82:
        raise ValueError(f"{root}: no .gm82 project file (not a gm82save tree)")
    proj.project_file = gm82[0]
    proj.settings = {k: _num(v) for k, v in _kv(os.path.join(root, gm82[0])).items()}

    # ---- objects ----
    odir = os.path.join(root, "objects")
    if os.path.isdir(odir):
        for fn in sorted(os.listdir(odir)):
            if not fn.endswith(".txt") or fn in ("index.yyd", "tree.yyd"):
                continue
            name = fn[:-4]
            kv = _kv(os.path.join(odir, fn))
            o = Gm82Object(
                name=name,
                sprite=kv.get("sprite", ""),
                visible=kv.get("visible", "1") == "1",
                solid=kv.get("solid", "0") == "1",
                persistent=kv.get("persistent", "0") == "1",
                depth=int(_num(kv.get("depth", "0"))),
                parent=kv.get("parent", ""),
                mask=kv.get("mask", ""),
            )
            gml = os.path.join(odir, name + ".gml")
            if os.path.isfile(gml):
                o.events = parse_events(_read(gml))
            proj.objects[name] = o

    # ---- scripts ----
    sdir = os.path.join(root, "scripts")
    if os.path.isdir(sdir):
        for fn in sorted(os.listdir(sdir)):
            if fn.endswith(".gml"):
                proj.scripts[fn[:-4]] = _read(os.path.join(sdir, fn))

    # ---- rooms ----
    rdir = os.path.join(root, "rooms")
    if os.path.isdir(rdir):
        proj.room_order = [r for r in _tree_order(os.path.join(rdir, "tree.yyd"))
                           if os.path.isdir(os.path.join(rdir, r))]
        room_dirs = proj.room_order or sorted(
            d for d in os.listdir(rdir) if os.path.isdir(os.path.join(rdir, d)))
        for rname in room_dirs:
            proj.rooms[rname] = _load_room(os.path.join(rdir, rname), rname)

    # ---- sprites / backgrounds (metadata + checksums only) ----
    if with_assets:
        # sprites: one subdirectory per sprite (sprite.txt + numbered frames)
        adir = os.path.join(root, "sprites")
        if os.path.isdir(adir):
            for name in sorted(os.listdir(adir)):
                d = os.path.join(adir, name)
                if not os.path.isdir(d):
                    continue
                meta_file = os.path.join(d, "sprite.txt")
                props = {k: _num(v) for k, v in _kv(meta_file).items()} \
                    if os.path.isfile(meta_file) else {}
                frames = sorted(fn for fn in os.listdir(d) if fn.endswith(".png"))
                spr = Gm82Sprite(
                    name=name, props=props, frame_count=len(frames),
                    frame_sha256=[_sha256_file(os.path.join(d, fn)) for fn in frames],
                )
                if "bbox_right" in props and "bbox_left" in props:
                    spr.width = int(props["bbox_right"]) - int(props["bbox_left"]) + 1
                    spr.height = int(props["bbox_bottom"]) - int(props["bbox_top"]) + 1
                proj.sprites[name] = spr
        # backgrounds: flat <name>.txt + <name>.png pairs
        bdir = os.path.join(root, "backgrounds")
        if os.path.isdir(bdir):
            for fn in sorted(os.listdir(bdir)):
                if not fn.endswith(".txt") or fn in ("index.yyd", "tree.yyd"):
                    continue
                name = fn[:-4]
                props = {k: _num(v) for k, v in _kv(os.path.join(bdir, fn)).items()}
                png = os.path.join(bdir, name + ".png")
                proj.backgrounds[name] = Gm82Sprite(
                    name=name, props=props,
                    frame_count=1 if os.path.isfile(png) else 0,
                    frame_sha256=[_sha256_file(png)] if os.path.isfile(png) else [],
                )

    # ---- triggers / misc resource lists ----
    tdir = os.path.join(root, "triggers")
    if os.path.isdir(tdir):
        for fn in sorted(os.listdir(tdir)):
            if fn.endswith((".gml", ".txt")) and fn not in ("index.yyd", "tree.yyd"):
                proj.triggers[fn] = _read(os.path.join(tdir, fn))
    for attr, sub in (("paths", "paths"), ("fonts", "fonts"),
                      ("datafiles", "datafiles")):
        adir = os.path.join(root, sub)
        if os.path.isdir(adir):
            setattr(proj, attr, sorted(
                fn for fn in os.listdir(adir) if fn not in ("index.yyd", "tree.yyd")))
    return proj


def _load_room(rd: str, name: str) -> Gm82Room:
    room = Gm82Room(name=name)
    kv = _kv(os.path.join(rd, "room.txt"))
    room.settings = {k: _num(v) for k, v in kv.items()}
    room.width = int(_num(kv.get("width", "0")))
    room.height = int(_num(kv.get("height", "0")))
    room.speed = int(_num(kv.get("roomspeed", "0")))
    code = os.path.join(rd, "code.gml")
    if os.path.isfile(code):
        room.creation_code = _read(code)

    for i in range(8):
        if kv.get(f"bg_source{i}"):
            room.backgrounds.append({
                "slot": i,
                "source": kv.get(f"bg_source{i}"),
                "visible": kv.get(f"bg_visible{i}") == "1",
                "foreground": kv.get(f"bg_is_foreground{i}") == "1",
                "tile_h": kv.get(f"bg_tile_h{i}") == "1",
                "tile_v": kv.get(f"bg_tile_v{i}") == "1",
                "stretch": kv.get(f"bg_stretch{i}") == "1",
            })
    for i in range(8):
        if kv.get(f"view_visible{i}") == "1" or (i == 0 and f"view_xview{i}" in kv):
            view = {k[:-len(str(i))]: _num(v) for k, v in kv.items()
                    if k.endswith(str(i)) and k.startswith("view_")}
            if view:
                view["slot"] = i
                view["visible"] = kv.get(f"view_visible{i}") == "1"
                room.views.append(view)

    inst_file = os.path.join(rd, "instances.txt")
    if os.path.isfile(inst_file):
        for line in _read(inst_file).splitlines():
            if not line.strip():
                continue
            p = line.split(",")
            # object,x,y,id_hex,locked,xscale,yscale,blend,angle,has_code
            inst = Gm82Instance(
                object=p[0], x=float(p[1]), y=float(p[2]), id_hex=p[3],
                locked=int(p[4]) if len(p) > 4 else 0,
                xscale=float(p[5]) if len(p) > 5 else 1.0,
                yscale=float(p[6]) if len(p) > 6 else 1.0,
                blend=int(p[7]) if len(p) > 7 else 4294967295,
                angle=float(p[8]) if len(p) > 8 else 0.0,
            )
            has_code = len(p) > 9 and p[9].strip() == "1"
            cc = os.path.join(rd, inst.id_hex + ".gml")
            if has_code or os.path.isfile(cc):
                if os.path.isfile(cc):
                    inst.creation_code = _read(cc)
            room.instances.append(inst)

    layers_file = os.path.join(rd, "layers.txt")
    if os.path.isfile(layers_file):
        for depth_s in _read(layers_file).split():
            depth = int(depth_s)
            tf = os.path.join(rd, f"{depth_s}.txt")
            if not os.path.isfile(tf):
                continue
            n = 0
            for line in _read(tf).splitlines():
                if not line.strip():
                    continue
                p = line.split(",")
                room.tiles.append(Gm82Tile(
                    background=p[0], x=float(p[1]), y=float(p[2]),
                    u=float(p[3]), v=float(p[4]),
                    width=float(p[5]), height=float(p[6]),
                    depth=depth,
                    xscale=float(p[8]) if len(p) > 8 else 1.0,
                    yscale=float(p[9]) if len(p) > 9 else 1.0,
                    blend=int(p[10]) if len(p) > 10 else 4294967295,
                ))
                n += 1
            room.tile_layers[depth] = n
    return room
