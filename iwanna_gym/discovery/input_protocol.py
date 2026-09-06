"""Permitted recurrent-agent input protocol.

Recurrent policies for the discovery benchmark may receive, IN ADDITION
to the observation, a small fixed set of previous-transition inputs
that are standard for memory-based RL and contain NO hidden task
information:

  - previous action (one-hot over the action space),
  - previous reward (clipped),
  - an observed attempt-boundary flag (1 on the first step of a new
    attempt within the task, i.e. right after a death/timeout respawn;
    0 otherwise) — this is the OBSERVED fact "a new attempt just began",
    which the agent can see (it was respawned), not the hidden reason.

These inputs are FORBIDDEN from carrying: hazard identities, dormant
flags, trigger geometry, hidden task parameters, task ids, or the death
location beyond what the observation already shows. They are computed
purely from the agent's own previous action, the scalar reward it
received, and the boundary flag the environment surfaces.

The protocol is defined so it is IDENTICAL between the carry-memory and
reset-memory agents: the extra inputs depend only on (prev_action,
prev_reward, attempt_boundary), never on the recurrent hidden state, so
the two ablation arms receive the same inputs and differ ONLY at the
memory-reset boundary (the intended single variable).

The old pilot's recurrent baseline is the OBSERVATION-ONLY protocol
(no extra inputs); this module is the distinct, opt-in augmented
protocol. Enabling it changes the input dimension and therefore is a
new agent, reported separately — never conflated with the obs-only
results.
"""
from __future__ import annotations

import numpy as np

REWARD_CLIP = 1.0


def extra_dim(n_actions: int) -> int:
    """Width of the extra-input vector: one-hot prev action + prev
    reward + attempt-boundary flag."""
    return n_actions + 2


def extra_inputs(prev_action: int | None, prev_reward: float,
                 attempt_boundary: bool, n_actions: int) -> np.ndarray:
    """Build the permitted recurrent extra-input vector for one env.

    prev_action None (first step of a task) -> zero one-hot. The vector
    is deterministic in its arguments and reads nothing hidden."""
    v = np.zeros(extra_dim(n_actions), np.float32)
    if prev_action is not None and 0 <= prev_action < n_actions:
        v[prev_action] = 1.0
    v[n_actions] = float(np.clip(prev_reward, -REWARD_CLIP, REWARD_CLIP))
    v[n_actions + 1] = 1.0 if attempt_boundary else 0.0
    return v


def batch_extra_inputs(prev_actions, prev_rewards, attempt_boundaries,
                       n_actions: int) -> np.ndarray:
    """Vectorized extra inputs for a batch of N envs -> (N, extra_dim).
    prev_actions: int array (use -1 for 'none'). attempt_boundaries:
    0/1 array (the env's per-step attempt_ended on the PREVIOUS step)."""
    n = len(prev_actions)
    out = np.zeros((n, extra_dim(n_actions)), np.float32)
    pa = np.asarray(prev_actions)
    valid = (pa >= 0) & (pa < n_actions)
    out[np.arange(n)[valid], pa[valid]] = 1.0
    out[:, n_actions] = np.clip(np.asarray(prev_rewards, np.float32),
                                -REWARD_CLIP, REWARD_CLIP)
    out[:, n_actions + 1] = np.asarray(attempt_boundaries, np.float32)
    return out
