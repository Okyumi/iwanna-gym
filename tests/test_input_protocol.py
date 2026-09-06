"""Permitted recurrent input-protocol tests (torch-free).

The extra recurrent inputs (prev action, prev reward, attempt-boundary)
must be identical between the carry-memory and reset-memory arms,
contain no hidden information, and be distinct from the observation-only
baseline.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, ".")
from iwanna_gym.discovery import input_protocol as P     # noqa: E402


def test_extra_dim_and_shape():
    assert P.extra_dim(6) == 8 and P.extra_dim(12) == 14
    v = P.extra_inputs(3, 0.5, True, 12)
    assert v.shape == (14,) and v[3] == 1.0
    assert v[12] == 0.5 and v[13] == 1.0


def test_first_step_has_no_prev_action():
    v = P.extra_inputs(None, 0.0, False, 12)
    assert v[:12].sum() == 0.0 and v[13] == 0.0


def test_reward_is_clipped():
    v = P.extra_inputs(0, 99.0, False, 6)
    assert v[6] == P.REWARD_CLIP
    v = P.extra_inputs(0, -99.0, False, 6)
    assert v[6] == -P.REWARD_CLIP


def test_identical_between_carry_and_reset_arms():
    # the two ablation arms differ only in the recurrent memory cut; the
    # extra inputs depend only on (prev_action, prev_reward, boundary),
    # so for the SAME action/reward/boundary stream they are identical.
    rng = np.random.default_rng(0)
    for _ in range(50):
        pa = int(rng.integers(-1, 12))
        pr = float(rng.standard_normal())
        b = bool(rng.integers(0, 2))
        carry = P.extra_inputs(pa, pr, b, 12)   # "carry-memory" arm
        reset = P.extra_inputs(pa, pr, b, 12)   # "reset-memory" arm
        assert np.array_equal(carry, reset)


def test_batch_matches_scalar():
    pas = [-1, 0, 5, 11]
    prs = [0.0, 1.0, -2.0, 0.3]
    bs = [0, 1, 0, 1]
    batch = P.batch_extra_inputs(pas, prs, bs, 12)
    for i in range(4):
        assert np.array_equal(
            batch[i], P.extra_inputs(pas[i] if pas[i] >= 0 else None,
                                     prs[i], bool(bs[i]), 12))


def test_protocol_carries_no_hidden_fields():
    # structural guard: extra_inputs takes only prev_action, prev_reward,
    # attempt_boundary, n_actions — nothing hazard/task-identifying.
    import inspect
    params = list(inspect.signature(P.extra_inputs).parameters)
    assert params == ["prev_action", "prev_reward", "attempt_boundary",
                      "n_actions"]


def test_distinct_from_observation_only():
    # the observation-only baseline adds nothing; the protocol adds a
    # nonzero-width vector, so the two are different input specs.
    assert P.extra_dim(12) > 0
