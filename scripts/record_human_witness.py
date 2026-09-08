"""Record a HUMAN playthrough of a native (or controlled) discovery task
and save a deterministic, replay-verified completion witness.

The witness is action integers only (metadata-safe to commit); source
mechanics are never modified — this only READS keyboard input and steps
the env. On task success the recorded action stream is handed to
`witness.write_witness`, which REPLAYS it deterministically and writes the
witness only if the replay also reaches success (so every committed
witness is reproducible). Deaths during play are kept in the stream and
counted as `deaths_before_success`.

Requires a display + `pygame` (on your own machine). This is headless in
the authoring sandbox, so it prints setup instructions there instead of
opening a window.

Controls: Left/Right = move, Up or Space = jump (tap to jump, tap again in
air to double-jump), hold Shift = shoot, R = give up this attempt (forces a
respawn by standing), Esc = quit without saving.

Usage:
    python scripts/record_human_witness.py disc.iwbtgr_1_5_3.rGuy1.first_screen
    [--task-seed 1] [--scale 1] [--fps 50]
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, ".")


def _action(h: int, jump: int, shoot: int) -> int:
    # a = shoot*6 + 2*(h+1) + jump   (matches c_src/iwanna.h action encoding)
    return shoot * 6 + 2 * (h + 1) + jump


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    ap.add_argument("--task-seed", type=int, default=1)
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--fps", type=int, default=50)
    a = ap.parse_args()

    try:
        import pygame
    except Exception:
        print("pygame is required for interactive recording and is not "
              "available here (headless sandbox). On your machine:\n"
              "  pip install pygame\n"
              f"  python scripts/record_human_witness.py {a.task_id}")
        return 2

    import numpy as np
    import iwanna_gym.discovery.registry as R
    from iwanna_gym.discovery import witness as W
    from iwanna_gym.discovery.viz import TaskRenderer

    reg = R.load_registry()
    spec = reg[a.task_id]
    env = R.make_env(a.task_id, obs_mode="observable_vector", registry=reg)
    obs, info = env.reset(seed=0, options={"task_seed": a.task_seed})
    rend = TaskRenderer(env, visible_only=True)

    frame0 = rend.frame()
    h0, w0 = frame0.shape[0], frame0.shape[1]
    pygame.init()
    screen = pygame.display.set_mode((w0 * a.scale, h0 * a.scale))
    pygame.display.set_caption(f"record: {a.task_id}")
    clock = pygame.time.Clock()

    actions: list[int] = []
    jump_prev = False
    success = False
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE]:
            print("quit without saving")
            env.close(); pygame.quit(); return 1
        h = (1 if keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_LEFT] else 0)
        jump_held = keys[pygame.K_UP] or keys[pygame.K_SPACE]
        shoot = 1 if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else 0
        # jump is edge-triggered by the core; passing the held bit through is
        # correct (press = 0->1 edge), so just forward the held state
        a_int = _action(h, 1 if jump_held else 0, shoot)
        jump_prev = jump_held

        obs, r, term, tru, info = env.step(a_int)
        actions.append(a_int)

        frame = rend.frame()
        surf = pygame.surfarray.make_surface(
            np.transpose(frame[:, :, :3], (1, 0, 2)))
        if a.scale != 1:
            surf = pygame.transform.scale(
                surf, (w0 * a.scale, h0 * a.scale))
        screen.blit(surf, (0, 0))
        pygame.display.flip()
        clock.tick(a.fps)

        if term:
            success = bool(info.get("task_success"))
            running = False

    env.close()
    pygame.quit()
    if not success:
        print("task not completed — no witness written")
        return 1
    rec = W.write_witness(spec, actions, a.task_seed, source="human_play")
    print(f"witness written + replay-verified: {rec['frames']} frames, "
          f"{rec['deaths_before_success']} deaths before success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
