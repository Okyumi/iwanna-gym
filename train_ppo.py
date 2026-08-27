"""Quick PPO baseline on iwanna_gym with Stable-Baselines3.

Usage:
    python train_ppo.py --level gaps --steps 400000
    python train_ppo.py --level needle --steps 1000000 --eval-episodes 50

For serious training, use the PufferLib binding instead (c_src/binding.c +
config/iwanna.ini): drop c_src/ into pufferlib/ocean/iwanna/ and run
`puffer train puffer_iwanna`.
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
    p.add_argument("--steps", type=int, default=400_000)
    p.add_argument("--n-envs", type=int, default=16)
    p.add_argument("--max-steps", type=int, default=700)
    p.add_argument("--eval-episodes", type=int, default=20)
    p.add_argument("--death-penalty", type=float, default=1.0,
                   help="lower it (e.g. 0.3) on spike-heavy levels where PPO "
                        "otherwise learns to stand still")
    p.add_argument("--ent", type=float, default=0.01)
    p.add_argument("--save", default=None)
    args = p.parse_args()

    def make():
        return Monitor(
            iw.IWannaEnv(
                level=args.level,
                reward_mode="dense",
                death_penalty=args.death_penalty,
                max_steps=args.max_steps,
            ),
            info_keywords=("is_success",),
        )

    venv = make_vec_env(make, n_envs=args.n_envs)
    model = PPO(
        "MlpPolicy",
        venv,
        learning_rate=3e-4,
        n_steps=256,
        batch_size=2048,
        n_epochs=4,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=args.ent,
        policy_kwargs=dict(net_arch=[256, 256]),
        verbose=1,
        device="cpu",
    )
    model.learn(total_timesteps=args.steps, log_interval=10)
    if args.save:
        model.save(args.save)

    # -- evaluation --
    # note: sample from the policy (deterministic=False). In this fully
    # deterministic env the argmax policy can lock into loops; the learned
    # stochastic policy is what PPO actually optimizes.
    env = iw.IWannaEnv(level=args.level, reward_mode="dense",
                       death_penalty=args.death_penalty, max_steps=args.max_steps)
    successes, lengths = 0, []
    for ep in range(args.eval_episodes):
        obs, _ = env.reset(seed=1000 + ep)
        for t in range(args.max_steps):
            action, _ = model.predict(obs, deterministic=False)
            obs, r, term, trunc, info = env.step(int(action))
            if term:
                if info["last_event"] == 2:
                    successes += 1
                    lengths.append(t + 1)
                break
    print(f"\neval: {successes}/{args.eval_episodes} goals reached")
    if lengths:
        print(f"mean frames to goal: {np.mean(lengths):.0f} "
              f"({np.mean(lengths) / 50:.1f}s at 50 fps)")
    env.close()


if __name__ == "__main__":
    main()
