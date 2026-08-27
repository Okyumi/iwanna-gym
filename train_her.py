"""HER baseline: DQN + HerReplayBuffer on the goal-conditioned env.

The env resamples a reachable goal tile every episode (random_goal=True) and
rewards only on reaching it (sparse). HER relabels failed trajectories with
achieved goals, which is what makes sparse goal-reaching learnable.

Usage:
    python train_her.py --level gaps --steps 300000
"""
from __future__ import annotations

import argparse

import numpy as np
from stable_baselines3 import DQN
from stable_baselines3.her import HerReplayBuffer

import iwanna_gym as iw


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--level", default="gaps")
    p.add_argument("--steps", type=int, default=300_000)
    p.add_argument("--max-steps", type=int, default=600)
    p.add_argument("--eval-episodes", type=int, default=50)
    p.add_argument("--save", default=None)
    args = p.parse_args()

    env = iw.IWannaGoalEnv(level=args.level, sparse=True, random_goal=True,
                           max_steps=args.max_steps, death_penalty=1.0)
    model = DQN(
        "MultiInputPolicy",
        env,
        replay_buffer_class=HerReplayBuffer,
        replay_buffer_kwargs=dict(
            n_sampled_goal=4,
            goal_selection_strategy="future",
        ),
        buffer_size=300_000,
        learning_starts=5_000,
        batch_size=512,
        gamma=0.98,
        learning_rate=5e-4,
        train_freq=8,
        gradient_steps=2,
        target_update_interval=2_000,
        exploration_fraction=0.25,
        exploration_final_eps=0.05,
        policy_kwargs=dict(net_arch=[256, 256]),
        verbose=1,
        device="cpu",
    )
    model.learn(total_timesteps=args.steps, log_interval=50)
    if args.save:
        model.save(args.save)

    # eval on fresh random goals (epsilon-greedy with small epsilon)
    succ = 0
    for ep in range(args.eval_episodes):
        obs, _ = env.reset(seed=5_000 + ep)
        for t in range(args.max_steps):
            if np.random.rand() < 0.02:
                action = env.action_space.sample()
            else:
                action, _ = model.predict(obs, deterministic=True)
            obs, r, term, trunc, info = env.step(int(action))
            if term:
                succ += info["last_event"] == 2
                break
    print(f"\nHER eval: {succ}/{args.eval_episodes} random goals reached")
    env.close()


if __name__ == "__main__":
    main()
