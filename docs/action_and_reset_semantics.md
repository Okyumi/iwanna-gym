# Action space and reset semantics

## Action space

One discrete space, decoded in the C core as

```
action = shoot_held * 6 + 2 * (h + 1) + jump_held        h ∈ {-1, 0, +1}
```

| a | input | a | input |
|---|---|---|---|
| 0 | left | 6 | left + shoot |
| 1 | left + jump | 7 | left + jump + shoot |
| 2 | idle | 8 | idle + shoot |
| 3 | idle + jump | 9 | idle + jump + shoot |
| 4 | right | 10 | right + shoot |
| 5 | right + jump | 11 | right + jump + shoot |

**Actions 0–5 are exactly the historical 6-action space**, so the full
12-action space is a superset and legacy experiments reproduce bit-for-bit.
Press/release EDGES for both jump and shoot are derived inside the core
from consecutive held-states, replicating GameMaker's keyboard events.

Environment selection:

* classic/research levels default to `Discrete(6)` (`action_mode="legacy"`);
* exact-game packs default to `Discrete(12)` (`action_mode="full"`);
* either can be overridden with `IWannaEnv(..., action_mode=...)`.

The alternative of separate shoot-press actions was rejected: the source
input model is key-held states (the engine computes edges), a 12-action
product space keeps the legacy space as a strict prefix, and PufferLib's
discrete pipelines take Discrete(12) directly.

## Shooting (IWBTGR source semantics)

Read from `playerShoot.gml` / `objects/bullet.gml` / `sprBulletMask` —
not inferred:

* one bullet per shoot PRESS edge (the source's autofire is a non-legit
  DIP setting and is not imported);
* at most **4** bullets alive (`bullet_number() < 4`);
* spawn at `(x, y-2)` with `hspeed = facing * 16`, no gravity;
* lifetime **42 frames** (`alarm[0] = 42`), destroyed on solid contact
  (tiles and imported solid rects) and culled outside the room;
* hitbox: mask origin (5,1), bbox 0..9 × 0..1 → rect `[x-5..x+4] × [y-1..y]`;
* facing updates from horizontal input before the shot in the same frame
  (player Step order);
* bullets are NOT consumed by saves (they fly through);
* shooting while overlapping a save activates it directly (the source's
  contact-save path in `playerShoot`).

Interactions with shootable triggers, destructible blocks, enemies and
bosses belong to the dynamic-object milestones (those objects are not
imported yet); `blockNise` (fake block) destroying bullets is a known
deviation until fake blocks are imported.

## Save semantics (IWBTGR source)

From `saveVeryHard.gml` (Collision_bullet → User Event 0) and
`scripts/saveGame.gml`:

* **shot-activated**: a Kid bullet touching the save's bbox — or shooting
  while overlapping it — activates it; this is the canonical exact-game
  default (`save_mode="shoot"`);
* per-save **50-frame** cooldown (`saveTimer`) between activations;
* activation stores the **player's exact position and facing** at that
  moment (`savex`/`savey`/`savew`) and the current room — NOT the save's
  position;
* save state (active sprite), `save_activated` events, and the stored
  checkpoint persist across room transitions and deaths;
* difficulty gating is per-save (`saveMedium` diff 0 only, `saveHard`
  ≤1, `saveVeryHard`/`saveVeryEvil` ≤2, none on Impossible), from the
  source `Create` events;
* legacy **touch saves** remain available for research/debug
  (`save_mode="touch"`, still the default for classic single-room levels;
  they respawn at the save's position, the historical behavior).

Known deviations (documented, pending later milestones): the
`SoftlockBlocker`/`playerKiller` save-validity check and the invalid-shot
bullet deflection are not implemented (SoftlockBlocker is not imported);
evil-save dynamics (hp, movement) are not imported.

## Death, respawn, attempt vs task reset

Source flow (`killPlayer.gml` → `gameOver` → `key_reset` →
`reset_game.gml` → `room_goto(saveroom)` → `room_start.gml` +
`load_game_execute.gml`):

* death destroys the player, increments the death counter, and waits for
  retry; retry reloads the save room — a **full room reset** (objects,
  gates, bullets recreated) — and recreates the player at the exact saved
  position with saved facing, `vspeed=hspeed=0`, `djump=1`;
* progression state (`savedata` → runtime gflags) and the active save
  persist across death;
* the death-screen delay is skipped in the RL loop (retry happens on the
  next frame) — a documented runtime deviation with no effect on world
  state.

The runtime exposes the two reset kinds explicitly:

* **Attempt reset** — same task, same checkpoint, same adaptation
  problem. Triggered automatically by death when `checkpoint_respawn=True`
  (counts a death) or manually via `env.attempt_reset()` /
  `CIWanna.attempt_reset()` (the source "R" quick-retry: no death
  counted). Pack mode restores the source-faithful checkpoint state as
  above; classic mode keeps its historical no-room-reset behavior.
  Agent-side memory may persist across attempts.
* **Task reset** — `env.reset()`: new episode from the configured start
  (full-game start room or the selected room), progression flags, saves,
  attempt and death counters cleared. Training systems should clear
  adaptation state here.

Evaluation metadata in `info` (no hidden trap/world state is leaked):

```
game_id  room_id  checkpoint_id  attempt_id  death_count  difficulty
```

`attempt_id` starts at 1 per task reset and increments on every death
respawn and manual attempt reset; `checkpoint_id` identifies the active
checkpoint as `room:​x:​y` of the stored respawn.
