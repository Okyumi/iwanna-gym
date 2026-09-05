"""Versioned task registry for the discovery benchmark suites.

Resolves the audited candidate manifest
(``manifests/discovery_task_candidates.toml``, milestone 13) into
EXECUTABLE task specs for the three suites of
``docs/discovery_benchmark_contract.md``:

  - ``iwbtg_native``  — source-native IWBTGR screens/segments: the
    complete headline suite. Source geometry, triggers, physics, save
    behavior and hazard timing are NEVER altered; the registry only
    anchors where an attempt starts (a source save / playerStart cell)
    and what counts as success (a source screen region or save cell).
  - ``controlled``    — research rooms (`iwannagym_research_v1`),
    original content in fangame style; never called original IWBTG.
  - ``ood``           — K2 WARPED transfer. Only coverage-approved,
    actually-implemented mechanics qualify; the static-only import
    means this suite is EMPTY in this release (candidates stay
    `pending`, never playable benchmark evidence).

Both consumers read this registry directly:
  - Gymnasium: ``IWannaDiscoveryEnv(task="disc….")`` /
    ``registry.make_env(task_id)``;
  - PufferLib/Ocean: ``registry.binding_kwargs(task_id)`` returns the
    numeric kwargs for ``c_src/binding.c`` plus the pack path for the
    ``IWG_PACK`` environment variable. Any compiled ``.iwpack`` —
    including a future ``iwbtg_original_2007`` pack — loads through the
    same mechanism with no binding changes.

A task is **active** (eligible for headline scoring) only when it has
a committed completion witness (``manifests/discovery/witnesses``) and
a blind-policy diagnostic record; accepted tasks without one remain
registered with status ``pending_witness`` and are excluded from
scoring — never silently dropped.
"""
from __future__ import annotations

import hashlib
import json
import os
import tomllib
from dataclasses import dataclass, field
from typing import Any

SUITE_VERSION = "discovery_suite_v1"

MANIFEST = os.path.join("manifests", "discovery_task_candidates.toml")
WITNESS_DIR = os.path.join("manifests", "discovery", "witnesses")
DIAG_DIR = os.path.join("manifests", "discovery", "diagnostics")

SCREEN_W, SCREEN_H = 800, 608
SPLITS = ("train", "validation", "test")
SUITES = ("iwbtg_native", "controlled", "ood")

#: spawn offset inside a 32px anchor cell: player origin so the 11x21
#: hitbox (y-12..y+8) stands on the tile row below the cell
ANCHOR_DX, ANCHOR_DY = 16.0, 23.0

#: per-task spawn adjustments (px, relative to the anchor cell corner)
#: where the default offset intersects a source hazard's cycle at the
#: anchor itself — the anchor save and all content are unchanged; only
#: the standing position beside it moves. Justification per entry.
SPAWN_ADJUST: dict[str, tuple[float, float]] = {
    # the CycleSpike mask sweeps the save cell; one tile right is the
    # position a player occupies after activating this save in source
    "disc.iwbtgr_1_5_3.rGraveyard.cycle_crypt": (48.0, 23.0),
}


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    suite: str
    split: str
    game: str                    # game id or "iwannagym_research_v1"
    room: str                    # room name or level path
    attempts_K: int
    attempt_frames_H: int
    hazard_families: tuple[str, ...]
    fidelity: str
    provenance: dict = field(compare=False)
    # execution anchors (None for controlled rooms: authored S/G used)
    start_xy: tuple[float, float] | None = None
    goal_rect: tuple[float, float, float, float] | None = None
    witness_status: str = "pending_witness"
    diagnostic_status: str = "pending"

    @property
    def active(self) -> bool:
        """Eligible for headline/suite scoring."""
        return (self.witness_status == "witnessed"
                and self.diagnostic_status == "recorded")


def _goal_rect(row: dict) -> tuple[float, float, float, float]:
    g = row["goal"]
    if g["kind"] == "reach_region":
        sx, sy = g["screen"]
        return (sx * SCREEN_W, sy * SCREEN_H,
                sx * SCREEN_W + SCREEN_W - 1, sy * SCREEN_H + SCREEN_H - 1)
    if g["kind"] == "activate_save":
        # executable predicate this release: enter the save's 32px cell
        # (reaching the checkpoint; activation itself is unchanged
        # source behavior the agent may also perform)
        x, y = float(g["x"]), float(g["y"])
        return (x, y, x + 31.0, y + 31.0)
    raise ValueError(f"unknown goal kind {g['kind']!r}")


def _witness_status(task_id: str) -> str:
    return ("witnessed"
            if os.path.exists(os.path.join(WITNESS_DIR, task_id + ".json"))
            else "pending_witness")


def _diag_status(task_id: str) -> str:
    p = os.path.join(DIAG_DIR, task_id + ".json")
    if not os.path.exists(p):
        return "pending"
    with open(p, encoding="utf-8") as f:
        rec = json.load(f)
    # a task every blind pattern strolls through unharmed has NO
    # committed evidence of hidden information: flagged, not scored
    return "flagged_trivial" if rec.get("trivially_passable") else "recorded"


def load_registry(manifest_path: str = MANIFEST) -> dict[str, TaskSpec]:
    """All ACCEPTED tasks, keyed by stable id. Deterministic order."""
    with open(manifest_path, "rb") as f:
        m = tomllib.load(f)
    reg: dict[str, TaskSpec] = {}
    for row in m.get("native", []):
        if row.get("decision") != "accept":
            continue
        cp = row["checkpoint"]
        reg[row["id"]] = TaskSpec(
            task_id=row["id"], suite="iwbtg_native", split=row["split"],
            game="iwbtgr_1_5_3", room=row["room"],
            attempts_K=int(row["budget"]["K"]),
            attempt_frames_H=int(row["budget"]["H"]),
            hazard_families=tuple(row.get("hazard_families", [])),
            fidelity=row["fidelity"]["label"],
            provenance={
                "source": row["fidelity"].get("provenance", ""),
                "checkpoint_anchor": cp["anchor"],
                "checkpoint_xy": [cp["x"], cp["y"]],
                "goal": row["goal"],
                "manifest_evidence": row.get("evidence", ""),
            },
            start_xy=(float(cp["x"]) + SPAWN_ADJUST.get(
                          row["id"], (ANCHOR_DX, ANCHOR_DY))[0],
                      float(cp["y"]) + SPAWN_ADJUST.get(
                          row["id"], (ANCHOR_DX, ANCHOR_DY))[1]),
            goal_rect=_goal_rect(row),
            witness_status=_witness_status(row["id"]),
            diagnostic_status=_diag_status(row["id"]),
        )
    for row in m.get("controlled", []):
        if row.get("decision") != "accept":
            continue
        reg[row["id"]] = TaskSpec(
            task_id=row["id"], suite="controlled", split=row["split"],
            game="iwannagym_research_v1", room=row["room"],
            attempts_K=int(row["budget"]["K"]),
            attempt_frames_H=int(row["budget"]["H"]),
            hazard_families=tuple(row.get("hazard_families", [])),
            fidelity=row["fidelity"]["label"],
            provenance={
                "source": row["fidelity"].get("provenance", ""),
                "probe": "scripts/probe_traps.py",
            },
            witness_status=_witness_status(row["id"]),
            diagnostic_status=_diag_status(row["id"]),
        )
    # ood: every row is pending in this release (static import only);
    # registered so the suite exists, with zero executable tasks
    for row in m.get("ood", []):
        if row.get("decision") == "accept":       # none today, by policy
            raise ValueError(
                "an OOD row is marked accept but K2W dynamics are not "
                "imported; refusing to register unplayable content")
    return reg


def pending_ood(manifest_path: str = MANIFEST) -> list[dict]:
    with open(manifest_path, "rb") as f:
        m = tomllib.load(f)
    return [dict(id=r["id"], reason=r.get("reason", ""))
            for r in m.get("ood", []) if r.get("decision") == "pending"]


def suite_tasks(suite: str, registry: dict[str, TaskSpec] | None = None,
                split: str | None = None,
                active_only: bool = False) -> list[TaskSpec]:
    if suite not in SUITES:
        raise ValueError(f"unknown suite {suite!r} (choose from {SUITES})")
    reg = registry if registry is not None else load_registry()
    out = [t for t in reg.values() if t.suite == suite]
    if split is not None:
        if split not in SPLITS:
            raise ValueError(f"unknown split {split!r}")
        out = [t for t in out if t.split == split]
    if active_only:
        out = [t for t in out if t.active]
    return sorted(out, key=lambda t: t.task_id)


def registry_hash(registry: dict[str, TaskSpec] | None = None) -> str:
    """Content hash of the executable registry (ids, anchors, budgets,
    splits) — pinned by tests so silent drift fails CI."""
    reg = registry if registry is not None else load_registry()
    doc = [
        [t.task_id, t.suite, t.split, t.game, t.room, t.attempts_K,
         t.attempt_frames_H, list(t.start_xy or ()),
         list(t.goal_rect or ())]
        for t in sorted(reg.values(), key=lambda t: t.task_id)
    ]
    return hashlib.sha256(
        json.dumps([SUITE_VERSION, doc]).encode()).hexdigest()


# ------------------------------------------------------------------ #
# execution: shared kwargs for the Gymnasium env and the binding
# ------------------------------------------------------------------ #

def _native_room_index(spec: TaskSpec) -> int:
    from iwanna_gym.games import get_game
    return get_game(spec.game).room_index(spec.room)


def task_env_kwargs(spec: TaskSpec) -> dict[str, Any]:
    """kwargs for IWannaDiscoveryEnv(**kwargs) (minus obs_mode)."""
    if spec.suite == "iwbtg_native":
        return dict(game=spec.game, mode="room", room_id=spec.room,
                    difficulty=0,           # medium: every source save present
                    attempts_K=spec.attempts_K,
                    attempt_frames_H=spec.attempt_frames_H,
                    reward_mode="sparse")
    if spec.suite == "controlled":
        return dict(level=spec.room, attempts_K=spec.attempts_K,
                    attempt_frames_H=spec.attempt_frames_H,
                    reward_mode="sparse")
    raise ValueError(f"suite {spec.suite} has no executable tasks yet")


def apply_task_anchors(c, spec: TaskSpec) -> None:
    """Configure a CIWanna handle with the spec's start/goal anchors
    (before reset). No-op for controlled rooms (authored S/G)."""
    if spec.start_xy is not None:
        room = _native_room_index(spec)
        c.set_task_start(room, *spec.start_xy)
        if spec.goal_rect is not None:
            c.set_task_goal(room, *spec.goal_rect)


def make_env(task_id: str, obs_mode: str = "observable_vector",
             registry: dict[str, TaskSpec] | None = None):
    """The reference Gymnasium path: a fully configured discovery env."""
    from iwanna_gym.env import IWannaDiscoveryEnv
    reg = registry if registry is not None else load_registry()
    spec = reg[task_id]
    return IWannaDiscoveryEnv(obs_mode=obs_mode, _task_spec=spec,
                              **task_env_kwargs(spec))


def binding_kwargs(task_id: str,
                   registry: dict[str, TaskSpec] | None = None
                   ) -> tuple[dict[str, float], dict[str, str]]:
    """The PufferLib/Ocean path: (numeric kwargs for c_src/binding.c,
    environment variables to set — file paths cannot travel through the
    binding's numeric kwargs). Environment variables:
      IWG_PACK        compiled .iwpack (native tasks; any game — a
                      future iwbtg_original_2007 pack loads identically)
      IWG_LEVEL_FILE  controlled research-room text file
    """
    reg = registry if registry is not None else load_registry()
    spec = reg[task_id]
    base = dict(level=0, max_steps=spec.attempts_K * spec.attempt_frames_H,
                reward_mode=0, death_penalty=1.0, random_goal=0,
                discovery=1, attempts_K=spec.attempts_K,
                attempt_frames_H=spec.attempt_frames_H,
                obs_mode=1, task_seed=0,
                use_pack=0, use_level_file=0, difficulty=0,
                task_start_set=0, task_start_room=-1,
                task_start_x=0.0, task_start_y=0.0,
                task_goal_set=0, task_goal_room=-1,
                task_gx0=0.0, task_gy0=0.0, task_gx1=0.0, task_gy1=0.0)
    if spec.suite == "iwbtg_native":
        from iwanna_gym.games import get_game
        gmod = get_game(spec.game)
        room = gmod.room_index(spec.room)
        base.update(use_pack=1, task_start_set=1, task_start_room=room,
                    task_start_x=spec.start_xy[0],
                    task_start_y=spec.start_xy[1],
                    task_goal_set=1, task_goal_room=room,
                    task_gx0=spec.goal_rect[0], task_gy0=spec.goal_rect[1],
                    task_gx1=spec.goal_rect[2], task_gy1=spec.goal_rect[3])
        pack = os.environ.get("IWANNA_IWBTGR_PACK") or gmod.PACK_PATH
        return base, {"IWG_PACK": pack}
    if spec.suite == "controlled":
        from iwanna_gym.levels import level_path
        base.update(use_level_file=1)
        return base, {"IWG_LEVEL_FILE": level_path(spec.room)}
    raise ValueError(f"suite {spec.suite} has no executable tasks yet")


def load_witness(task_id: str) -> dict:
    with open(os.path.join(WITNESS_DIR, task_id + ".json"),
              encoding="utf-8") as f:
        return json.load(f)
