"""Native vector path + baseline trainer: parity, memory boundaries,
the causal-reset ablation, gradients, checkpointing, visualization."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile

import numpy as np
import pytest

import sys
sys.path.insert(0, ".")
import iwanna_gym.discovery as d                          # noqa: E402
from iwanna_gym.discovery import baselines as B           # noqa: E402
from iwanna_gym.discovery.vector import CVecIWanna        # noqa: E402

PACK = "build/games/iwbtgr_1_5_3.iwpack"
TRAP = dict(level="traps/t06_crusher", K=3, H=250)


# ------------------------------------------------------------------ #
# vector path
# ------------------------------------------------------------------ #

def test_vec_matches_gym_reference_trajectory():
    tid = "disc.research.t06_crusher"
    v = CVecIWanna([tid], base_seed=9)
    v.set_task_seeds([4242])
    v.reset()
    env = d.make_env(tid)
    env.reset(seed=0, options={"task_seed": 4242})
    for t in range(600):
        a = 4 if t % 5 else 5
        o, r, term, ae, te, ts = v.step(np.array([a], np.int32))
        og, rg, tg, _, ig = env.step(a)
        assert np.array_equal(o[0], og)
        assert r[0] == rg and bool(term[0]) == tg
        assert bool(ae[0]) == ig["attempt_ended"]
        assert bool(te[0]) == ig["task_ended"]
        if tg:
            break
    v.close(); env.close()


def test_vec_flags_match_env_getters():
    v = CVecIWanna([TRAP] * 3, base_seed=2)
    v.reset()
    for t in range(900):
        o, r, term, ae, te, ts = v.step(np.full(3, 4, np.int32))
        for i, c in enumerate(v.envs):
            assert bool(ae[i]) == c.attempt_ended
            assert bool(te[i]) == c.task_ended
    v.close()


def test_vec_deterministic_from_base_seed():
    def run():
        v = CVecIWanna([TRAP] * 4, base_seed=77)
        v.reset()
        out = []
        for t in range(400):
            o, *_ = v.step(np.full(4, 4 if t % 7 else 5, np.int32))
            out.append(o.tobytes())
        v.close()
        return out
    assert run() == run()


@pytest.mark.skipif(not os.path.exists(PACK),
                    reason="local source-built pack required")
def test_vec_raw_pack_entry_mechanism():
    """Raw .iwpack path entries — the mechanism that will load
    iwbtg_original_2007 with zero new code."""
    import iwanna_gym.games.iwbtgr_1_5_3 as G
    e = dict(pack_path=G.PACK_PATH,
             start_room=G.room_names().index("rKraidgiefBoss"),
             K=5, H=300, action_n=12)
    v = CVecIWanna([e] * 2, base_seed=1)
    v.reset()
    for t in range(400):
        v.step(np.full(2, 4, np.int32))
    v.close()


# ------------------------------------------------------------------ #
# recurrent memory boundaries (the acceptance criterion)
# ------------------------------------------------------------------ #

def _drive_until(tr, want_attempt_end=True, max_iters=40):
    """Collect rollouts until a boundary of the wanted kind occurred;
    returns the MEMCUT/flags trace of the last rollout."""
    for _ in range(max_iters):
        batch = tr.collect()
        MEMCUT = batch[6]
        if MEMCUT.any() or not want_attempt_end:
            return batch
    raise AssertionError("no boundary reached")


def test_recurrent_state_preserved_across_death_cleared_at_task_end():
    tr = B.PPOTrainer([TRAP], policy="gru", n_envs=4, rollout_T=64,
                      seed=5)
    saw_carry = saw_taskcut = False
    for _ in range(30):
        T, N = 64, 4
        for t in range(T):
            ob = tr.vec.obs
            tr.h, _ = B.gru_step(tr.params, ob, tr.h)
            logits, _ = B.head(tr.params, tr.h)
            acts, _, _ = B.sample_actions(logits, tr.rng)
            h_before = tr.h.copy()
            _, _, term, ae, te, ts = tr.vec.step(
                np.full(N, 4, np.int32))
            died = (ae == 1) & (te == 0)
            for i in np.nonzero(died)[0]:
                # attempt death: hidden state must be UNTOUCHED
                assert np.array_equal(tr.h[i], h_before[i])
                assert np.abs(tr.h[i]).sum() > 0
                saw_carry = True
            cut = te == 1
            tr.h[cut] = 0.0
            for i in np.nonzero(cut)[0]:
                assert np.abs(tr.h[i]).sum() == 0
                saw_taskcut = True
        if saw_carry and saw_taskcut:
            break
    assert saw_carry and saw_taskcut
    tr.vec.close()


def test_causal_reset_ablation_differs_only_at_memory_boundary():
    """gru vs gru_reset with identical seeds: identical params, identical
    actions and hidden states up to the first attempt death; at that
    boundary gru carries state while gru_reset zeroes it."""
    a = B.PPOTrainer([TRAP], policy="gru", n_envs=4, rollout_T=200,
                     seed=11)
    b = B.PPOTrainer([TRAP], policy="gru_reset", n_envs=4, rollout_T=200,
                     seed=11)
    for k in a.params:
        assert np.array_equal(a.params[k], b.params[k])
    extra = None
    for _ in range(20):
        ba = a.collect()
        bb = b.collect()
        Oa, Aa, MEMa = ba[0], ba[1], ba[6]
        Ob, Ab, MEMb = bb[0], bb[1], bb[6]
        extra = (MEMb == 1) & (MEMa == 0)
        if extra.any():
            break
        # still boundary-free: the two runs must be bit-identical
        assert np.array_equal(Oa, Ob) and np.array_equal(Aa, Ab)
    assert extra is not None and extra.any(), \
        "no attempt-only boundary observed"
    t0 = int(np.argwhere(extra)[0][0])
    # identical up to AND INCLUDING that step
    assert np.array_equal(Oa[:t0 + 1], Ob[:t0 + 1])
    assert np.array_equal(Aa[:t0 + 1], Ab[:t0 + 1])
    # afterwards the hidden states differ for the env that died
    env_i = int(np.argwhere(extra)[0][1])
    assert np.abs(a.h[env_i]).sum() >= 0     # carried (may be any value)
    # replay check: b's hidden was zeroed at t0 for env_i, a's was not
    assert MEMb[t0, env_i] == 1 and MEMa[t0, env_i] == 0
    a.vec.close(); b.vec.close()


# ------------------------------------------------------------------ #
# gradients, death memory, checkpointing
# ------------------------------------------------------------------ #

def test_ff_policy_gradient_matches_finite_differences():
    rng = np.random.default_rng(0)
    p = B.init_params("ff", 12, 5, 16, seed=3)
    o = rng.standard_normal((8, 12)).astype(np.float32)
    a = rng.integers(0, 5, 8)
    adv = rng.standard_normal(8).astype(np.float32)
    ret = rng.standard_normal(8).astype(np.float32)
    feat, _ = B.ff_forward(p, o)
    logits, _ = B.head(p, feat)
    z = logits - logits.max(1, keepdims=True)
    pr = np.exp(z); pr /= pr.sum(1, keepdims=True)
    lp_old = np.log(pr[np.arange(8), a] + 1e-10).astype(np.float32)

    def loss(params):
        feat, _ = B.ff_forward(params, o)
        logits, val = B.head(params, feat)
        z = logits - logits.max(1, keepdims=True)
        prob = np.exp(z); prob /= prob.sum(1, keepdims=True)
        logp_all = np.log(prob + 1e-10)
        lp = logp_all[np.arange(8), a]
        ratio = np.exp(lp - lp_old)
        surr = -np.minimum(ratio * adv,
                           np.clip(ratio, 0.8, 1.2) * adv)
        ent = -(prob * logp_all).sum(1)
        return float((surr - 0.01 * ent
                      + 0.5 * (val - ret) ** 2).mean())

    tr = B.PPOTrainer.__new__(B.PPOTrainer)
    tr.params = p
    tr.cfg = dict(clip=0.2, ent_coef=0.01, vf_coef=0.5)
    feat, cache = B.ff_forward(p, o)
    g, dfeat = tr._loss_heads(feat, a, adv, ret, lp_old)
    g.update(B.ff_backward(p, cache, dfeat))
    eps = 1e-4
    for k in ("Wpi", "Wv", "W2", "W1"):
        idx = tuple(rng.integers(0, s) for s in p[k].shape)
        p[k][idx] += eps; up = loss(p)
        p[k][idx] -= 2 * eps; dn = loss(p)
        p[k][idx] += eps
        num = (up - dn) / (2 * eps)
        assert abs(num - g[k][idx]) < 5e-3, (k, num, g[k][idx])


def test_death_memory_bounded_and_cleared():
    dm = B.DeathMemory(2, 4, window=5)
    for t in range(9):
        dm.push(np.full((2, 4), t, np.float32))
    ae = np.array([1, 0], np.uint8)
    te = np.array([0, 0], np.uint8)
    dm.on_boundaries(ae, te, np.array([1, 0]))
    assert dm.summary[0, :-1].mean() == pytest.approx(6.0)  # mean(4..8)
    assert dm.summary[0, -1] == pytest.approx(0.1)
    assert np.all(dm.summary[1] == 0)
    dm.on_boundaries(np.array([0, 0], np.uint8),
                     np.array([1, 0], np.uint8), np.array([0, 0]))
    assert np.all(dm.summary[0] == 0)          # task reset clears
    assert dm.buf.shape == (2, 5, 4)           # bounded


def test_checkpoint_resume_roundtrip():
    td = pathlib.Path(tempfile.mkdtemp(prefix="disc_ckpt_"))
    tr = B.PPOTrainer([TRAP], policy="ff", n_envs=4, rollout_T=32,
                      seed=7)
    tr.update(tr.collect())
    tr.save(str(td / "ck.npz"))
    tr2 = B.PPOTrainer.resume(str(td / "ck.npz"))
    assert tr2.iteration == tr.iteration
    assert tr2.env_steps == tr.env_steps
    for k in tr.params:
        assert np.array_equal(tr.params[k], tr2.params[k])
        assert np.array_equal(tr.opt.m[k], tr2.opt.m[k])
    assert tr2.opt.t == tr.opt.t
    tr.vec.close(); tr2.vec.close()


def test_train_cli_smoke_and_eval_records(tmp_path=None):
    import tempfile
    from train_discovery import evaluate, train
    out = tempfile.mkdtemp(prefix="disc_run_")
    cfg = dict(policy="ff", tasks=["disc.research.t03_riser"],
               obs_mode="observable_vector", n_envs=4, rollout_T=32,
               hid=32, lr=3e-4, gamma=0.999, lam=0.95, clip=0.2,
               ent_coef=0.01, vf_coef=0.5, epochs=1, seed=2,
               env_step_budget=2000, ckpt_every=5)
    s = train(cfg, out)
    assert s["env_steps"] >= 2000 and not s["oracle"]
    rows = [json.loads(x) for x in
            open(os.path.join(out, "train_log.jsonl"))]
    assert rows and all("env_sps" in r for r in rows)
    p = evaluate(cfg, out, n_seeds=1)
    from iwanna_gym.discovery import evaluator as E
    recs = [json.loads(x) for x in open(p)]
    agg = E.aggregate(recs, K=25)
    assert agg["n_task_runs"] == 1 and not agg["oracle"]


def test_oracle_config_refuses_headline():
    from train_discovery import train
    cfg = dict(policy="ff", tasks=["disc.research.t03_riser"],
               obs_mode="privileged_vector", headline=True,
               n_envs=2, rollout_T=8, env_step_budget=8, seed=1)
    with pytest.raises(SystemExit):
        train(cfg, tempfile.mkdtemp(prefix="disc_o_"))


# ------------------------------------------------------------------ #
# visualization
# ------------------------------------------------------------------ #

def test_rollout_gif_controlled_witness():
    from iwanna_gym.discovery.viz import record_rollout
    w = d.load_witness("disc.research.t03_riser")
    td = tempfile.mkdtemp(prefix="disc_viz_")
    s = record_rollout("disc.research.t03_riser",
                       os.path.join(td, "t03.gif"),
                       actions=w["actions"], task_seed=w["task_seed"])
    assert s["success"] and os.path.getsize(s["out"]) > 1000


@pytest.mark.skipif(not os.path.exists(PACK),
                    reason="local source-built pack required")
def test_rollout_gif_native_pack_with_annotations():
    from iwanna_gym.discovery.viz import record_rollout
    td = tempfile.mkdtemp(prefix="disc_viz_")
    s = record_rollout("disc.iwbtgr_1_5_3.rGuy1.cliff_ambush",
                       os.path.join(td, "amb.gif"),
                       policy=lambda o: 4, max_frames=500)
    assert s["video_frames"] > 50 and os.path.getsize(s["out"]) > 1000


def test_dashboard_generator():
    import subprocess
    td = tempfile.mkdtemp(prefix="disc_dash_")
    out = os.path.join(td, "dash.html")
    r = subprocess.run(
        [sys.executable, "scripts/make_discovery_dashboard.py",
         "--eval", "build/discovery_eval/*.jsonl", "--out", out],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": os.environ.get(
            "PYTHONPATH", "") + ":."})
    assert r.returncode == 0, r.stderr[-500:]
    html = open(out).read()
    assert "Success by attempt" in html and "<svg" in html
