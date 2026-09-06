# Pilot pre-registration — discovery benchmark

Committed BEFORE the pilot's final results were inspected (verify by
git history: this file lands one commit ahead of
`build/discovery_pilot/` and the pilot report). This is an evidence
milestone: a negative result triggers diagnosis of the task contract or
the agents, never rhetorical repair.

## Hypotheses (fixed in advance)

- **H1 (memory helps on discovery tasks).** Recurrent PPO with hidden
  state carried across attempt deaths (`gru`) achieves higher
  normalized adaptation AUC and Success@K than the byte-identical
  reset-on-death ablation (`gru_reset`) on ACTIVE controlled-discovery
  tasks. This is the causal comparison: identical initialization,
  parameters, optimizer, budgets; the runs differ only at the
  death-boundary memory cut (proven bit-identical up to the first death
  by `tests/test_discovery_training.py`).
- **H2 (the gap shrinks on precision-only controls).** On
  precision/timing rooms with no hidden information (the four
  audit-excluded rooms t07_bullets, t15_rain, t16_bridge,
  t19_speedgate), the gru−gru_reset gap is smaller than on discovery
  tasks (ideally ≈0): there is nothing for cross-attempt memory to
  carry.
- **H3 (explicit death memory reduces repeated deaths).** The
  `deathmem` baseline attains a lower repeated-death rate at
  already-revealed hazards than `ff`, at matched budgets.
- **H4 (held-out transfer is harder).** Policies trained only on the
  TRAIN-split discovery tasks score lower S(1) and lower AUC on the
  held-out validation/test tasks (screens never trained; test rows'
  hazard families held out) than on their training tasks.

## Fixed comparisons, budgets, seeds

All runs: observable_vector observations, sparse reward (no shaping),
hidden width 128, Adam(3e-4), rollout 128 x 24 envs, epochs 2,
K=25 / H=2000 per task, matched total env-interaction budgets within
each suite. Seeds: 3 per policy for the discovery suite, 2 elsewhere
(compute-bound; every seed's raw output retained). Policies: ff, gru,
gru_reset, deathmem (deathmem adds input width for its bounded memory
vector; gru vs gru_reset is the parameter-exact causal pair —
parameter counts reported in the report's audit section).

| pilot | train tasks | eval tasks | budget/run |
|---|---|---|---|
| P1 discovery | the 9 ACTIVE train-split controlled tasks | all 14 active controlled tasks, broken out train vs held-out (val+test) | 5,000,000 env steps |
| P2 precision controls | t07_bullets, t15_rain, t16_bridge, t19_speedgate (loaded as raw rooms; never called discovery tasks) | the same four rooms | 3,000,000 env steps |
| P3 native | disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall (the sole ACTIVE native task) | the same task, fresh task seeds | 3,000,000 env steps |

Native held-out transfer CANNOT run in this pilot: all validation/test
native tasks are pending completion witnesses (suite report §5), and we
will not score unwitnessed tasks. H4 is therefore tested on the
controlled suite only; the native version is listed as a remaining
experiment. K2 WARPED is omitted: zero coverage-approved OOD tasks
exist (static-only import) — no OOD evidence will be claimed.

Evaluation: after training, each policy runs every eval task at task
seeds {11, 12, 13} (never seen in training seeding) through the
milestone-15 evaluator; raw per-attempt records are retained under
`build/discovery_pilot/` (metadata-only: outcomes, frames, death
coordinates). Reported metrics, fixed in advance: Success@K,
success-by-attempt S(k), normalized adaptation AUC and AUC−S(1),
attempts and frames to first success (censored), repeated-death rate,
and training throughput (env/learner/end-to-end SPS).

## Decision rules (fixed in advance)

- H1 supported if gru's mean AUC exceeds gru_reset's by more than one
  pooled standard error on P1 eval, consistently in direction across
  seeds; refuted in the opposite direction; underpowered otherwise.
- H2 supported if the P2 gap is smaller than the P1 gap; specifically
  the interaction (P1 gap − P2 gap) > 0.
- H3 supported if deathmem RDR < ff RDR by more than one pooled SE.
- H4 supported if, for each trained policy, held-out S(1) and AUC are
  below the same policy's train-task values.
- Smoke-scale caveat: 3–5M steps on 2 CPU cores is a PILOT. If
  absolute success rates stay so low that the metrics are floor-bound
  (e.g. S@K < 0.05 everywhere), the verdict is "underpowered — scale
  compute", not a claim in either direction.

## What will NOT be done

No config/seed selection after seeing results (all launched from this
file's table); no pooling of suites; no privileged observations in any
scored run; no turning smoke runs into conclusions; no OOD claims; no
altering task content. If gru ≤ gru_reset on discovery tasks, the
report will say so and diagnose (task informativeness, agent capacity,
budget) rather than reframe.
