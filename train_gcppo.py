"""Goal-conditioned PPO baseline on the dict-obs env with random goals.

PPO cannot relabel goals like HER, so this uses dense distance-delta shaping
toward the (random) desired goal. Success metric: fraction of episodes whose
random goal is reached.

Usage:
    python train_gcppo.py --level gaps --steps 600000
"""
from __future__ import annotations

import argparse

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor

import iwanna_gym as iw


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--level", default="gaps")
    p.add_argument("--steps", type=int, default=600_000)
    p.add_argument("--n-envs", type=int, default=16)
    p.add_argument("--max-steps", type=int, default=600)
    p.add_argument("--eval-episodes", type=int, default=50)
    p.add_argument("--save", default=None)
    args = p.parse_args()

    def make():
        return Monitor(
            iw.IWannaGoalEnv(level=args.level, sparse=False, random_goal=True,
                             max_steps=args.max_steps, death_penalty=1.0),
            info_keywords=("is_success",),
        )

    venv = make_vec_env(make, n_envs=args.n_envs)
    model = PPO(
        "MultiInputPolicy",
        venv,
        learning_rate=3e-4,
        n_steps=256,
        batch_size=2048,
        n_epochs=4,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.01,
        policy_kwargs=dict(net_arch=[256, 256]),
        verbose=1,
        device="cpu",
    )
    model.learn(total_timesteps=args.steps, log_interval=10)
    if args.save:
        model.save(args.save)

    # eval: sample policy (argmax can loop in this deterministic env)
    env = iw.IWannaGoalEnv(level=args.level, sparse=False, random_goal=True,
                           max_steps=args.max_steps, death_penalty=1.0)
    succ, lens = 0, []
    for ep in range(args.eval_episodes):
        obs, _ = env.reset(seed=5_000 + ep)
        for t in range(args.max_steps):
            action, _ = model.predict(obs, deterministic=False)
            obs, r, term, trunc, info = env.step(int(action))
            if term:
                if info["last_event"] == 2:
                    succ += 1
                    lens.append(t + 1)
                break
    print(f"\nGC-PPO eval: {succ}/{args.eval_episodes} random goals reached")
    if lens:
        print(f"mean frames to goal: {np.mean(lens):.0f}")
    env.close()


if __name__ == "__main__":
    main()
