# Discovery training path: throughput, baselines, tooling

Status of the PufferLib-convention native training path (milestone
"complete and optimize the shared task path"). Hardware for every
number below: **2 CPU cores** (this environment), vector width N=16
(training runs N=28), discovery protocol ON, observation mode noted per
row. Reproduce: `PYTHONPATH=. python scripts/bench_discovery_vec.py`.

## 1. One interface, every task class

`iwanna_gym/discovery/vector.CVecIWanna` steps N independent,
heterogeneous envs with **one C call per frame** (`iw_vec_step`) into
one shared (N, 101) observation block — no Python callback and no
allocation in the frame loop, boundary flags (attempt/task/success)
written by C into caller arrays. Entries: registry task ids
(controlled + accepted `iwbtgr_1_5_3` tasks), raw level names, or raw
`.iwpack` paths with room/segment, budgets, difficulty, obs mode and
the full 12-action space — the identical mechanism loads
`k2warped_gms14` OOD tasks the day one is coverage-approved and an
`iwbtg_original_2007` pack the day it exists (asserted by test using a
boss room as the stand-in "foreign" entry). The reference Gymnasium
env and this path are trajectory-identical under one task seed
(parity test).

## 2. Throughput on the actual benchmark workload

Env steps/second, random actions, pure C loop (`iw_vec_bench`),
observable_vector unless noted — NOT tile-only numbers:

| workload | n | env steps/s |
|---|---|---|
| controlled trap rooms (events + entities) | 16 | 3,638,123 |
| IWBTGR rGuy1 task (1,124-instance non-boss room) | 16 | 58,563 |
| IWBTGR rGuyFortress1 task (fire hall) | 16 | 130,637 |
| IWBTGR rKraidgiefBoss (dynamic/boss-heavy) | 16 | 40,965 |
| mixed heterogeneous vector (controlled + native) | 16 | 140,861 |
| mixed, privileged obs | 16 | 143,546 |

Native vector vs the reference Gymnasium loop on the SAME exact-game
task (chalice_hall): **126,295 vs 38,752 steps/s (3.3×)** — the
Gymnasium path remains the reference implementation, not the training
path. Observable-mode filtering stays within noise of privileged mode.

## 3. Baselines (pure numpy PPO — no SB3, no Python-stepped vector)

`train_discovery.py` + `configs/discovery/*.json`; all four policies
share hidden width 128, Adam(3e-4), rollout 128×28, sparse reward,
observable_vector, matched env-interaction budgets; `gru` and
`gru_reset` share byte-identical initialization. Launch commands are in
the train script header. Policies: `ff` (memoryless), `gru` (state
carried across attempt deaths, cleared at task ends — verified by
test), `gru_reset` (the causal-reset ablation: identical except the
hidden state is also zeroed at every attempt boundary; a test proves
the two runs are bit-identical up to the first death and differ only at
that boundary), `deathmem` (explicit bounded episodic memory: mean of
the last 30 pre-death observations + a death counter, concatenated to
the observation, cleared at task reset).

End-to-end training speed (2 cores, 28 envs, controlled suite): env
collection ~120k SPS; learner ~24k SPS (GRU/BPTT) — end-to-end ~15–20k
SPS recurrent, ~105k SPS feed-forward; 2M env steps take 19 s (ff) /
~2.3 min (gru) wall-clock. **Resume semantics (documented, tested):**
`--resume` restores the policy parameters, the Adam optimizer moments,
and the iteration/env-step counters, then continues with FRESH rollouts
— it is NOT trajectory-exact (the vectorized env RNG state and in-flight
rollout are not serialized). This is the promised behavior and is
asserted by `tests/test_discovery_training.py::
test_checkpoint_resume_roundtrip` (params, Adam m/v, and counters match
after a save/resume round-trip). Post-training evaluation writes
milestone-15 evaluator records (`eval.jsonl` → `aggregate()`). The real
PufferLib path uses its own CleanRL checkpointing (torch) with the same
param/optimizer-restoration semantics.

**Smoke-budget results** (2M env steps — far below convergence; these
validate the machinery and MAKE NO scientific claim): active controlled
suite, 14 tasks × 2 seeds — ff S@K 0.000; gru 0.071 ± 0.050 (all of it
within-task: S(1)=0, adaptation gain 0.069); gru_reset 0.071 (gain
0.067); deathmem 0.071 (gain 0.067); repeated-death rate 1.0 for every
policy at this budget. Distinguishing the memory hypotheses needs the
full budgets in the configs, on more cores.

Oracle upper bounds are configs, not code paths:
`gru_oracle_controlled.json` runs privileged observations, is tagged
ORACLE in every output, refuses the headline label, and its eval
records land in `*.oracle.jsonl` which `aggregate()` will not mix with
standard records.

## 3b. Learner validation (Prompt-2 item 4 — explicit status)

- **Gradient checks — DONE (both paths).** The feed-forward
  policy+value gradients are finite-difference checked
  (`test_ff_policy_gradient_matches_finite_differences`, tol 5e-3). The
  **recurrent (GRU/BPTT) gradients are now finite-difference checked**
  through the exact `gru_step`/`gru_backward_step`/`_update_gru` code
  path, including a memory cut at an attempt boundary
  (`test_gru_bptt_gradient_matches_finite_differences`, tol 5e-3). This
  was the outstanding gap; before this milestone only the FF path was
  FD-verified.
- **Loss normalization — DONE (documented choice).** Advantages are
  normalized once per batch, `(ADV - mean)/(std + 1e-8)`
  (`baselines.PPOTrainer.update`), NOT per-minibatch; rewards are not
  normalized (sparse task reward); value loss weight `vf_coef=0.5`,
  entropy `ent_coef` as configured. GAE(γ,λ) with per-env masking at
  `done`.
- **Update schedule / counts — DONE (auditable).** `epochs` passes per
  batch (default 2); the FF path shuffles and splits each epoch into 4
  minibatches; the GRU path does full-sequence BPTT per epoch (no
  minibatching, so the recurrence is unbroken). The `iteration` and
  `env_steps` counters advance once per `update` and are checkpointed
  (asserted by `test_checkpoint_resume_roundtrip`).
- **Recurrent input protocol — SPEC + UNIT TESTS ONLY, NOT wired into
  the learner.** `iwanna_gym/discovery/input_protocol.py` defines the
  permitted previous-action / clipped-reward / attempt-boundary inputs
  and is unit-tested (`tests/test_input_protocol.py`), but it is **not**
  consumed by `PPOTrainer` today. It is therefore a documented,
  validated input contract — NOT an implemented, trained learner
  feature. Enabling it changes the input dimension, so it defines a new
  agent that must be reported separately from the observation-only
  baseline; the revised preregistration
  (`docs/discovery_prereg_v2.md`) is where that wiring is scheduled.
- **Reference vs maintained learner.** The custom NumPy PPO above is the
  reference/parity implementation and is retained for reproducing the
  legacy pilot numbers; the maintained training path is PufferLib's
  CleanRL PPO (real `puffer train` UNVERIFIED in-sandbox — torch
  blocked). The pilot's null H1 is **not** attributed to optimization:
  the learner's gradients are FD-validated, so the null is not a
  gradient bug, but at 2 cores / 2–5M steps the budget is the confound,
  and the null is treated as uninformative about the hypothesis rather
  than as evidence that optimization masks a memory effect.

## 4. Visualization (never in the training loop)

`iwanna_gym/discovery/viz.py`: one renderer for every task type —
controlled text rooms via the classic renderer, source-native pack
rooms via the camera-view pack renderer (player, entities, view crop),
with `visible_only=True` hiding entities the source would not draw so
videos show the observable scene. `record_rollout()` replays
(task seed, actions) or drives a policy offline and writes a GIF with
a task/attempt/death header bar and red/green death/success border
flashes. `scripts/make_discovery_dashboard.py` renders a static HTML
dashboard (inline SVG, no plotting libs): S(k) curves,
attempts-to-success, repeated-death rate, SPS over iterations, and
wall-clock learning progress from the JSONL outputs. Training runs
headless; recording is a separate offline pass over deterministic
replays.

## 5. Blocked locally / next

Real PufferLib training (`puffer train`) needs a machine with
PufferLib installed; this environment cannot install it (registry
blocked), so the binding is exercised via its exact C path
(CVecIWanna) plus the compile-check — the numbers above are that same
step path. Native-task learning results await witnesses for the 24
pending native tasks; chalice_hall trains today
(`gru_native_smoke.json`). Full-budget baseline runs and the
memory-vs-ablation comparison are compute-bound, not code-bound.
