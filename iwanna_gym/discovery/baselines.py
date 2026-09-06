"""Minimum baselines for the discovery benchmark — pure numpy, driven
by the native vectorized C path (CVecIWanna: one C call per frame).

No RL framework: the learner is a self-contained numpy PPO so the
headline path never falls back to Stable-Baselines3 or a Python-stepped
vector env. Policies:

  ff           feed-forward PPO (memoryless reference)
  gru          recurrent PPO; hidden state CARRIED across attempt
               deaths, cleared at task boundaries (the benchmark's
               memory rule)
  gru_reset    the causal-reset ablation: byte-identical to `gru`
               except the hidden state is ALSO zeroed at every attempt
               boundary — the two runs differ only at that boundary
  deathmem     feed-forward PPO + an explicit bounded episodic death
               memory: a running summary (mean) of the last W
               observations before each in-task death, concatenated to
               the observation for the next attempts; cleared at task
               reset

Architecture/optimizer/rollout budgets are matched: every policy uses
hidden width ``hid``, the same Adam settings, the same rollout shape
(T x N), the same observation mode and the same total env-interaction
budget; `gru`/`gru_reset` share identical parameter initialization.

Oracle upper bounds are configuration, not code: obs_mode
"privileged_vector" tags the run ORACLE and the trainer refuses to
label such a run headline (see train_discovery.py).
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

from iwanna_gym.clib import OBS_SIZE

from .vector import CVecIWanna

# ------------------------------------------------------------------ #
# numpy nets + Adam
# ------------------------------------------------------------------ #


def _orth(shape, rng, gain=1.0):
    a = rng.standard_normal(shape)
    u, _, vt = np.linalg.svd(a, full_matrices=False)
    q = u if u.shape == shape else vt
    return (gain * q[:shape[0], :shape[1]]).astype(np.float32)


def init_params(kind: str, obs_dim: int, act_n: int, hid: int,
                seed: int) -> dict:
    rng = np.random.default_rng(seed)
    p = {}
    if kind == "ff":
        p["W1"] = _orth((obs_dim, hid), rng, np.sqrt(2))
        p["b1"] = np.zeros(hid, np.float32)
        p["W2"] = _orth((hid, hid), rng, np.sqrt(2))
        p["b2"] = np.zeros(hid, np.float32)
    else:  # gru: embed + GRU cell
        p["We"] = _orth((obs_dim, hid), rng, np.sqrt(2))
        p["be"] = np.zeros(hid, np.float32)
        p["Wz"] = _orth((2 * hid, hid), rng)
        p["bz"] = np.zeros(hid, np.float32)
        p["Wr"] = _orth((2 * hid, hid), rng)
        p["br"] = np.zeros(hid, np.float32)
        p["Wh"] = _orth((2 * hid, hid), rng)
        p["bh"] = np.zeros(hid, np.float32)
    p["Wpi"] = _orth((hid, act_n), rng, 0.01)
    p["bpi"] = np.zeros(act_n, np.float32)
    p["Wv"] = _orth((hid, 1), rng, 1.0)
    p["bv"] = np.zeros(1, np.float32)
    return p


class Adam:
    def __init__(self, params: dict, lr=3e-4, b1=0.9, b2=0.999, eps=1e-8):
        self.lr, self.b1, self.b2, self.eps = lr, b1, b2, eps
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}
        self.t = 0

    def step(self, params: dict, grads: dict, max_norm=0.5):
        gn = np.sqrt(sum(float((g ** 2).sum()) for g in grads.values()))
        scale = min(1.0, max_norm / (gn + 1e-12))
        self.t += 1
        bc1 = 1 - self.b1 ** self.t
        bc2 = 1 - self.b2 ** self.t
        for k, g in grads.items():
            g = g * scale
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * g
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * g * g
            params[k] -= (self.lr * (self.m[k] / bc1)
                          / (np.sqrt(self.v[k] / bc2) + self.eps))

    def state(self):
        return {"m": self.m, "v": self.v, "t": self.t}

    def load(self, st):
        self.m, self.v, self.t = st["m"], st["v"], st["t"]


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


# forward passes -----------------------------------------------------

def ff_forward(p, obs):
    h1 = np.tanh(obs @ p["W1"] + p["b1"])
    h2 = np.tanh(h1 @ p["W2"] + p["b2"])
    return h2, (obs, h1, h2)


def ff_backward(p, cache, dh2):
    obs, h1, h2 = cache
    g = {}
    d2 = dh2 * (1 - h2 * h2)
    g["W2"] = h1.T @ d2
    g["b2"] = d2.sum(0)
    d1 = (d2 @ p["W2"].T) * (1 - h1 * h1)
    g["W1"] = obs.T @ d1
    g["b1"] = d1.sum(0)
    return g


def gru_step(p, obs, h):
    e = np.tanh(obs @ p["We"] + p["be"])
    xh = np.concatenate([e, h], 1)
    z = _sig(xh @ p["Wz"] + p["bz"])
    r = _sig(xh @ p["Wr"] + p["br"])
    xrh = np.concatenate([e, r * h], 1)
    hh = np.tanh(xrh @ p["Wh"] + p["bh"])
    hn = (1 - z) * h + z * hh
    return hn, (obs, e, h, z, r, hh, xh, xrh)


def gru_backward_step(p, cache, dhn, g):
    obs, e, h, z, r, hh, xh, xrh = cache
    hid = h.shape[1]
    dz = dhn * (hh - h) * z * (1 - z)
    dhh = dhn * z * (1 - hh * hh)
    dh = dhn * (1 - z)
    g["Wh"] += xrh.T @ dhh
    g["bh"] += dhh.sum(0)
    dxrh = dhh @ p["Wh"].T
    de = dxrh[:, :hid]
    drh = dxrh[:, hid:]
    dr = drh * h * r * (1 - r)
    dh += drh * r
    g["Wz"] += xh.T @ dz
    g["bz"] += dz.sum(0)
    g["Wr"] += xh.T @ dr
    g["br"] += dr.sum(0)
    dxh = dz @ p["Wz"].T + dr @ p["Wr"].T
    de += dxh[:, :hid]
    dh += dxh[:, hid:]
    dde = de * (1 - e * e)
    g["We"] += obs.T @ dde
    g["be"] += dde.sum(0)
    return dh


def head(p, feat):
    logits = feat @ p["Wpi"] + p["bpi"]
    value = (feat @ p["Wv"] + p["bv"])[:, 0]
    return logits, value


def sample_actions(logits, rng):
    z = logits - logits.max(1, keepdims=True)
    prob = np.exp(z)
    prob /= prob.sum(1, keepdims=True)
    u = rng.random(logits.shape[0])
    cum = prob.cumsum(1)
    # float rounding can leave cum[-1] < 1; clip the rare overflow draw
    acts = np.minimum((u[:, None] > cum).sum(1), logits.shape[1] - 1)
    logp = np.log(prob[np.arange(len(acts)), acts] + 1e-10)
    return acts.astype(np.int32), logp, prob


# ------------------------------------------------------------------ #
# explicit episodic death memory (`deathmem`)
# ------------------------------------------------------------------ #

class DeathMemory:
    """Bounded per-env summary of recent pre-death context: the mean of
    the last `window` observations before each in-task death, plus a
    normalized death counter. Concatenated to the observation; cleared
    at task boundaries. This is the simplest explicit alternative to
    learned recurrence — it conditions the next attempt on what
    preceded the previous deaths and on nothing else."""

    def __init__(self, n_envs: int, obs_dim: int, window: int = 30):
        self.window = window
        self.dim = obs_dim + 1
        self.buf = np.zeros((n_envs, window, obs_dim), np.float32)
        self.fill = np.zeros(n_envs, np.int64)
        self.summary = np.zeros((n_envs, self.dim), np.float32)

    def push(self, obs):
        self.buf = np.roll(self.buf, -1, axis=1)
        self.buf[:, -1] = obs
        self.fill = np.minimum(self.fill + 1, self.window)

    def on_boundaries(self, attempt_event, task_ended, deaths_so_far):
        """attempt_event is the C terminal-event code per env
        (0 none, 1 death, 2 success, 3 timeout, 4 complete). ONLY a
        death (1) that does not end the task writes a death-context
        summary — a timed-out attempt is not a death and must not
        (this was the pre-repair bug). The pre-death observation window
        still clears on any nonfinal boundary so it never bleeds a
        timed-out attempt's context into the next death's summary."""
        died = (attempt_event == 1) & (task_ended == 0)
        for i in np.nonzero(died)[0]:
            w = int(self.fill[i])
            if w:
                self.summary[i, :-1] = self.buf[i, -w:].mean(0)
            self.summary[i, -1] = min(deaths_so_far[i] / 10.0, 1.0)
        nonfinal = (attempt_event > 0) & (task_ended == 0)
        self.fill[nonfinal] = 0                # reset window each attempt
        ends = task_ended == 1
        self.summary[ends] = 0.0
        self.fill[ends] = 0
        self.buf[ends] = 0.0

    def augmented(self, obs):
        return np.concatenate([obs, self.summary], 1)


# ------------------------------------------------------------------ #
# PPO trainer over the native vector
# ------------------------------------------------------------------ #

POLICY_KINDS = ("ff", "gru", "gru_reset", "deathmem")


class PPOTrainer:
    def __init__(self, tasks: list, policy: str = "ff",
                 obs_mode: str = "observable_vector",
                 n_envs: int = 16, rollout_T: int = 128, hid: int = 128,
                 lr: float = 3e-4, gamma: float = 0.999,
                 lam: float = 0.95, clip: float = 0.2,
                 ent_coef: float = 0.01, vf_coef: float = 0.5,
                 epochs: int = 2, seed: int = 1):
        assert policy in POLICY_KINDS
        self.cfg = dict(tasks=list(tasks), policy=policy, obs_mode=obs_mode,
                        n_envs=n_envs, rollout_T=rollout_T, hid=hid, lr=lr,
                        gamma=gamma, lam=lam, clip=clip, ent_coef=ent_coef,
                        vf_coef=vf_coef, epochs=epochs, seed=seed)
        entries = [tasks[i % len(tasks)] for i in range(n_envs)]
        self.vec = CVecIWanna(entries, obs_mode=obs_mode, base_seed=seed)
        self.act_n = self.vec.action_n
        self.policy = policy
        self.oracle = obs_mode == "privileged_vector"
        self.deathmem = (DeathMemory(n_envs, OBS_SIZE)
                         if policy == "deathmem" else None)
        obs_dim = OBS_SIZE + (self.deathmem.dim if self.deathmem else 0)
        kind = "gru" if policy in ("gru", "gru_reset") else "ff"
        self.kind = kind
        self.params = init_params(kind, obs_dim, self.act_n, hid, seed)
        self.opt = Adam(self.params, lr=lr)
        self.rng = np.random.default_rng(seed + 999)
        self.h = np.zeros((n_envs, hid), np.float32)
        self.env_steps = 0
        self.iteration = 0
        self.deaths_in_task = np.zeros(n_envs, np.int64)
        self.attempts_in_task = np.ones(n_envs, np.int64)
        self.finished_tasks: list[dict] = []
        self.t_start = time.monotonic()
        self.vec.reset()

    # -- memory boundary rule (THE experimental variable) --
    def _cut_memory(self, attempt_ended, task_ended):
        cut = task_ended == 1
        if self.policy == "gru_reset":          # causal-reset ablation
            cut = cut | (attempt_ended == 1)
        self.h[cut] = 0.0

    def _obs_in(self, obs):
        if self.deathmem:
            return self.deathmem.augmented(obs)
        return obs

    def collect(self):
        T, N = self.cfg["rollout_T"], self.cfg["n_envs"]
        obs_dim = self.params["W1" if self.kind == "ff" else "We"].shape[0]
        O = np.zeros((T, N, obs_dim), np.float32)
        A = np.zeros((T, N), np.int32)
        LP = np.zeros((T, N), np.float32)
        V = np.zeros((T, N), np.float32)
        RW = np.zeros((T, N), np.float32)
        DONE = np.zeros((T, N), np.float32)     # task boundary (GAE cut)
        MEMCUT = np.zeros((T, N), np.float32)   # actual memory cuts
        H0 = self.h.copy()
        for t in range(T):
            ob = self._obs_in(self.vec.obs)
            O[t] = ob
            if self.kind == "ff":
                feat, _ = ff_forward(self.params, ob)
            else:
                self.h, _ = gru_step(self.params, ob, self.h)
                feat = self.h
            logits, val = head(self.params, feat)
            acts, logp, _ = sample_actions(logits, self.rng)
            A[t], LP[t], V[t] = acts, logp, val
            if self.deathmem:
                self.deathmem.push(self.vec.obs.copy())
            _, rew, term, ae, te, ts = self.vec.step(acts)
            ev = self.vec.attempt_event         # 1 death 2 succ 3 timeout 4 complete
            RW[t] = rew
            DONE[t] = te
            self.env_steps += N
            # task bookkeeping (cheap array ops only): a death is
            # event==1, NOT merely an attempt boundary (timeouts are
            # ae==1 too and must not be counted as deaths)
            died = (ev == 1) & (te == 0)
            self.deaths_in_task += died
            self.attempts_in_task += (ae == 1)
            for i in np.nonzero(te)[0]:
                self.finished_tasks.append(dict(
                    task_id=self.vec.task_ids[i],
                    success=bool(ts[i]),
                    attempts=int(self.vec.envs[i].last_task_attempts),
                    deaths=int(self.vec.envs[i].last_task_deaths),
                    env_step=self.env_steps))
                self.deaths_in_task[i] = 0
                self.attempts_in_task[i] = 1
            if self.deathmem:
                self.deathmem.on_boundaries(ev, te, self.deaths_in_task)
            cut = (te == 1)
            if self.policy == "gru_reset":
                cut = cut | (ae == 1)
            MEMCUT[t] = cut
            self.h[cut] = 0.0
        # bootstrap value
        ob = self._obs_in(self.vec.obs)
        if self.kind == "ff":
            feat, _ = ff_forward(self.params, ob)
        else:
            hb, _ = gru_step(self.params, ob, self.h)
            feat = hb
        _, last_v = head(self.params, feat)
        return O, A, LP, V, RW, DONE, MEMCUT, H0, last_v

    @staticmethod
    def gae(RW, V, DONE, last_v, gamma, lam):
        T, N = RW.shape
        ADV = np.zeros((T, N), np.float32)
        gae = np.zeros(N, np.float32)
        nextv = last_v
        for t in range(T - 1, -1, -1):
            mask = 1.0 - DONE[t]
            delta = RW[t] + gamma * nextv * mask - V[t]
            gae = delta + gamma * lam * mask * gae
            ADV[t] = gae
            nextv = V[t]
        return ADV, ADV + V

    def update(self, batch):
        O, A, LP, V, RW, DONE, MEMCUT, H0, last_v = batch
        cfg = self.cfg
        ADV, RET = self.gae(RW, V, DONE, last_v, cfg["gamma"], cfg["lam"])
        ADV = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
        T, N = A.shape
        for _ in range(cfg["epochs"]):
            if self.kind == "ff":
                o = O.reshape(T * N, -1)
                a = A.reshape(-1)
                adv = ADV.reshape(-1)
                ret = RET.reshape(-1)
                lp_old = LP.reshape(-1)
                idx = self.rng.permutation(T * N)
                for mb in np.array_split(idx, 4):
                    self._update_ff(o[mb], a[mb], adv[mb], ret[mb],
                                    lp_old[mb])
            else:
                self._update_gru(O, A, ADV, RET, LP, MEMCUT, H0)
        self.iteration += 1

    def _loss_heads(self, feat, a, adv, ret, lp_old):
        cfg = self.cfg
        logits, val = head(self.params, feat)
        z = logits - logits.max(1, keepdims=True)
        prob = np.exp(z)
        prob /= prob.sum(1, keepdims=True)
        logp_all = np.log(prob + 1e-10)
        lp = logp_all[np.arange(len(a)), a]
        ratio = np.exp(lp - lp_old)
        unclipped = ratio * adv
        clipped = np.clip(ratio, 1 - cfg["clip"], 1 + cfg["clip"]) * adv
        use = (unclipped <= clipped)
        coef = np.where(use, ratio * adv, 0.0)      # d(-min)/dlogp
        n = len(a)
        onehot = np.zeros_like(prob)
        onehot[np.arange(n), a] = 1.0
        dlogits = (-coef[:, None] * (onehot - prob)) / n
        ent = -(prob * logp_all).sum(1)
        dlogits += cfg["ent_coef"] * (
            prob * (logp_all + ent[:, None])) / n
        dval = cfg["vf_coef"] * 2.0 * (val - ret) / n
        g = {"Wpi": feat.T @ dlogits, "bpi": dlogits.sum(0),
             "Wv": feat.T @ dval[:, None], "bv": dval.sum(0, keepdims=True)}
        dfeat = dlogits @ self.params["Wpi"].T \
            + dval[:, None] @ self.params["Wv"].T
        return g, dfeat

    def _update_ff(self, o, a, adv, ret, lp_old):
        feat, cache = ff_forward(self.params, o)
        g, dfeat = self._loss_heads(feat, a, adv, ret, lp_old)
        g.update(ff_backward(self.params, cache, dfeat))
        self.opt.step(self.params, g)

    def _update_gru(self, O, A, ADV, RET, LP, MEMCUT, H0):
        T, N = A.shape
        h = H0.copy()
        caches = []
        feats = np.zeros((T, N, h.shape[1]), np.float32)
        cuts = MEMCUT
        # replay the EXACT memory cuts collection applied: task ends
        # for `gru`, task ends + attempt deaths for `gru_reset` — the
        # only place the ablation differs
        for t in range(T):
            h, cache = gru_step(self.params, O[t], h)
            caches.append(cache)
            feats[t] = h
            h = h * (1.0 - cuts[t][:, None])
        g = {k: np.zeros_like(v) for k, v in self.params.items()}
        dfeats = np.zeros_like(feats)
        for t in range(T):
            gh, dfeat = self._loss_heads(
                feats[t], A[t], ADV[t], RET[t], LP[t])
            for k in gh:
                g[k] += gh[k]
            dfeats[t] = dfeat
        dh = np.zeros_like(h)
        for t in range(T - 1, -1, -1):
            dh = dh * (1.0 - cuts[t][:, None])  # no grad across cuts
            dh = gru_backward_step(self.params, caches[t],
                                   dh + dfeats[t], g)
        self.opt.step(self.params, g)

    # -- checkpoint / resume ----------------------------------------
    def save(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        np.savez(path,
                 cfg=json.dumps(self.cfg),
                 iteration=self.iteration,
                 env_steps=self.env_steps,
                 opt_t=self.opt.t,
                 **{"p_" + k: v for k, v in self.params.items()},
                 **{"m_" + k: v for k, v in self.opt.m.items()},
                 **{"v_" + k: v for k, v in self.opt.v.items()})

    @classmethod
    def resume(cls, path: str):
        z = np.load(path, allow_pickle=False)
        cfg = json.loads(str(z["cfg"]))
        tr = cls(**cfg)
        for k in tr.params:
            tr.params[k] = z["p_" + k].copy()
            tr.opt.m[k] = z["m_" + k].copy()
            tr.opt.v[k] = z["v_" + k].copy()
        tr.opt.t = int(z["opt_t"])
        tr.iteration = int(z["iteration"])
        tr.env_steps = int(z["env_steps"])
        return tr

    # -- acting API for evaluation ----------------------------------
    def act(self, obs_row: np.ndarray, h_row=None, greedy=False):
        ob = obs_row[None]
        if self.kind == "ff":
            feat, _ = ff_forward(self.params, ob)
            hn = None
        else:
            hcur = h_row[None] if h_row is not None else \
                np.zeros((1, self.cfg["hid"]), np.float32)
            hn, _ = gru_step(self.params, ob, hcur)
            feat = hn
        logits, _ = head(self.params, feat)
        if greedy:
            a = int(np.argmax(logits[0]))
        else:
            a, _, _ = sample_actions(logits, self.rng)
            a = int(a[0])
        return a, (hn[0] if hn is not None else None)


class TrainerEvalMemory:
    """Shared adapter that drives a trained PPOTrainer under the
    evaluator's memory protocol (used by both scripts/run_pilot.py and
    train_discovery.py so evaluation is not re-implemented). Holds the
    recurrent hidden state and, for the deathmem policy, the bounded
    death-memory summary populated from real terminal events. The
    evaluator owns reset_task()/observe() timing; this object only
    enacts the memory rule."""

    def __init__(self, tr: "PPOTrainer"):
        self.tr = tr
        self.dm = (DeathMemory(1, OBS_SIZE) if tr.deathmem is not None
                   else None)
        self._deaths = np.zeros(1, np.int64)
        self.reset_task()

    def reset_task(self):
        self.h = None
        self._deaths[0] = 0
        if self.dm is not None:                # force-clear summary+buf
            self.dm.on_boundaries(np.array([2], np.uint8),
                                  np.array([1], np.uint8), self._deaths)

    def observe(self, info):
        if not info.get("attempt_ended"):
            return
        ev = int(info.get("attempt_event", 0))
        te = 1 if info.get("task_ended") else 0
        if ev == 1 and not te:
            self._deaths[0] += 1
        if self.dm is not None:
            self.dm.on_boundaries(np.array([ev], np.uint8),
                                  np.array([te], np.uint8), self._deaths)
        if self.tr.policy == "gru_reset" and not te:
            self.h = None                       # causal-reset ablation

    def act(self, obs):
        ob = obs
        if self.dm is not None:
            self.dm.push(obs[None].copy())
            ob = np.concatenate([obs, self.dm.summary[0]])
        a, self.h = self.tr.act(ob, self.h)
        return a
