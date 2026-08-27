"""Record a GIF of a trained SB3 agent.

Usage:
    python scripts/record_gif.py --model /tmp/ppo_boshy --level boshy --out docs/agent_boshy.gif
    python scripts/record_gif.py --model /tmp/gcppo_tower --level tower --goal-env --episodes 3 \
        --out docs/agent_gc_tower.gif
"""
from __future__ import annotations

import argparse

from PIL import Image
from stable_baselines3 import DQN, PPO

import iwanna_gym as iw


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--level", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--algo", default="ppo", choices=["ppo", "dqn"])
    p.add_argument("--goal-env", action="store_true")
    p.add_argument("--episodes", type=int, default=1,
                   help="successful episodes to record (goal env: varied goals)")
    p.add_argument("--max-steps", type=int, default=700)
    p.add_argument("--tries", type=int, default=200)
    p.add_argument("--scale", type=float, default=0.5)
    args = p.parse_args()

    if args.goal_env:
        env = iw.IWannaGoalEnv(level=args.level, sparse=False, random_goal=True,
                               max_steps=args.max_steps, render_mode="rgb_array")
    else:
        env = iw.IWannaEnv(level=args.level, reward_mode="dense",
                           max_steps=args.max_steps, render_mode="rgb_array")
    # pass env so models saved with HerReplayBuffer can be deserialized
    model = (PPO if args.algo == "ppo" else DQN).load(args.model, env=env,
                                                      device="cpu")

    all_frames = []
    got = 0
    for ep in range(args.tries):
        obs, _ = env.reset(seed=2_000 + ep)
        frames = [env.render()]
        event = 0
        for _ in range(args.max_steps):
            a, _ = model.predict(obs, deterministic=False)
            obs, r, term, trunc, info = env.step(int(a))
            frames.append(env.render())
            if term:
                event = info["last_event"]
                break
        if event == 2:
            all_frames += frames
            got += 1
            if got >= args.episodes:
                break
    env.close()
    if not all_frames:
        raise SystemExit("no successful episode found")

    h, w, _ = all_frames[0].shape
    size = (int(w * args.scale), int(h * args.scale))
    imgs = [Image.fromarray(f).resize(size) for f in all_frames[::2]]
    imgs[0].save(args.out, save_all=True, append_images=imgs[1:],
                 duration=40, loop=0)
    print(f"saved {args.out}: {got} episode(s), {len(imgs)} frames")


if __name__ == "__main__":
    main()
