# Discovery suite report — `discovery_suite_v1`

Status of the executable benchmark built from the audited candidates
(`manifests/discovery_task_candidates.toml`) under the contract
(`docs/discovery_benchmark_contract.md`). Registry:
`iwanna_gym/discovery/` (version `discovery_suite_v1`, content hash
pinned in `tests/test_discovery_suite.py`). Reminder that applies to
every line below: IWBTGR is *I Wanna Be The Guy: Remastered* 1.5.3 —
not the original 2007 MMF2 game, whose import remains gated.

## 1. Task counts

| suite | registered | witnessed | flagged | **active (scored)** | pending |
|---|---|---|---|---|---|
| `iwbtg_native` (headline) | 25 | 1 | 0 | **1** | 24 pending_witness |
| `controlled` | 16 | 16 | 2 trivially-passable | **14** | 0 |
| `ood` (K2 WARPED) | 0 (+3 candidates) | — | — | **0** | 3 pending dynamics |

**Active** = registered + committed completion witness + blind-policy
diagnostic that does not flag the task. Only active tasks enter scored
results; pending tasks stay registered, executable, and replayable —
they are never silently dropped, and never scored.

Splits over registered tasks: native 14 train / 6 validation / 5 test;
controlled 11 / 3 / 2. Hazard-family labels across the registry: 51
distinct families; five are held out test-only (decoy spikes,
sinking platforms + spawning traps, appearing block chains, deceptive
furniture, the falling painting).

## 2. Source-native / controlled / OOD separation

- Native tasks execute against the frozen `iwbtgr_1_5_3_v1` pack with
  **zero content modification**: the registry sets only (a) where the
  attempt begins — a source save / playerStart cell, standing beside it
  (`SPAWN_ADJUST` documents the single case, `cycle_crypt`, where the
  default standing spot intersects a source hazard's sweep) — and
  (b) the success predicate — entry into a source screen region or the
  anchor-save cell of the manifest goal. Geometry, triggers, physics,
  save behavior and hazard timing are byte-identical to the frozen
  pack; every task row carries its fidelity label and provenance.
- Controlled tasks live in the separately named `controlled` suite
  (`iwannagym_research_v1` rooms) and are never described as IWBTG
  content. `evaluator.aggregate()` raises on any attempt to pool
  records across suites.
- OOD: the three K2 WARPED candidate rooms remain `pending` — the K2W
  import is static-only, and unsupported static imports are not
  playable benchmark evidence. The registry REFUSES to register an
  accepted OOD row while that is true (enforced in code and test).

## 3. Split rationale and leakage rules

Splits come from the audited manifest and are enforced at load time:
no (room, start-anchor) pair is shared between train and any holdout
split, and the five held-out hazard families appear in no training
task. One anchor is shared *within* the holdout side
(`rGuy1.spike_corridor` [test] and `rGuy1.realyoku_shaft`
[validation] start at the same source save and diverge immediately);
train tasks never touch it as a start, though train task
`rGuy1.first_screen` ends at that save's cell. This adjacency is the
closest approach between splits and is disclosed here rather than
hidden by re-anchoring source content.

## 4. Per-task execution guarantees

Every registered task provides: task reset vs source-faithful attempt
reset (native core, milestone 14), attempt budget K and per-attempt
frame budget H from the manifest, a stable success predicate evaluated
in the core (goal region entry), deterministic replay from
(task seed, action sequence), and a metadata-only provenance record.
Committed evidence per task:

- **Completion witnesses** (`manifests/discovery/witnesses/`, replayed
  green by `scripts/verify_witnesses.py` and in tests): all 16
  controlled tasks via the scripted rule probes (recorded action
  sequences, 228–426 frames), and 1 native task
  (`rGuyFortress1.chalice_hall`, found by the deterministic macro beam
  search in `iwanna_gym/discovery/witness.py`, 426 frames through the
  fire-arming hall). Witness records contain action integers only.
- **Blind-policy diagnostics** (`manifests/discovery/diagnostics/`,
  4 deterministic blind policies per task): 29 of 41 tasks show
  repeatable deaths under the fixed hidden configuration (the exact
  situation where remembering a failure pays); 2 controlled tasks
  (`t05_door`, `t08_chase`) are passed unharmed by EVERY blind pattern
  and are flagged out of the active set — no committed evidence of
  hidden information; 10 tasks produce no blind deaths because blind
  play stalls before their hazards (native gauntlets mostly), so their
  informative-failure evidence rests on the manifest audit plus the
  witness contrast where available, and is otherwise pending stronger
  probes. `t11_teleport`'s failure is non-lethal by design (the
  teleport, not a death) and is documented as such.

## 5. The native witness gap (the open item)

The macro beam search solved 1 of 25 native tasks within its budget
(2 passes, up to 280 s/task). That is a statement about the search,
not the tasks: IWBTGR gauntlets demand precise routing the macro
vocabulary cannot express (the search's frontier reproducibly dies at
the first genuine trap wall — e.g. the GraveTrap/Grabby row at
x≈2690 in `gravetrap_row`). Until a task is witnessed it is not
scored; the headline suite is therefore computable but currently
covers 1 native task. Next narrow steps, in preference order: record
human play through the existing raylib demo as witness action
sequences; strengthen the solver (finer action lattice near death
frontiers, checkpoint-graph search). No task is altered to make
witnessing easier — that path is forbidden by the contract.

## 6. Evaluator

`iwanna_gym/discovery/evaluator.py` (no RL library): per task and per
attempt it records outcome, attempt length, frames, death position and
trajectory index, and progress; per run it computes Success@K, the
success-by-attempt curve S(k) and normalized AUC, attempts/frames to
first success (censored at K), repeated-death rate (radius 32 px),
post-discovery improvement, and per-split transfer numbers (S(1) vs
AUC−S(1) — the pair that separates improvement across attempts from
ordinary learning across gradient updates: training moves S(1),
within-task adaptation moves the gain). Aggregation is task-level
means with standard errors over task runs; frames from one trajectory
are never independent samples. Suites and oracle records refuse to
pool; oracle output is forced into `*.oracle.jsonl`.

Reference run (`scripts/run_discovery_eval.py`, active controlled
suite, 14 tasks × 3 seeds): blind sprint — Success@K 0.143 ± 0.055,
S(1)=AUC=0.143, adaptation gain −0.000, repeated-death rate 0.996;
blind hop-sprint — Success@K 0.286 ± 0.071, gain 0.057 (its hop phase
drifts across attempts — a degenerate "adaptation" the RDR exposes:
0.996 of its repeat deaths hit an already-seen hazard). Exactly the
memoryless signature the benchmark is built to measure against.

## 7. Memory-oracle diagnostic

`evaluator.run_task(..., oracle=True)` runs the privileged observation
vector and hands the memory object the env's entity dump plus the
in-task death log — an UPPER-BOUND diagnostic only. It is labeled in
every record (`oracle: true`), segregated on disk
(`*.oracle.jsonl`), and `aggregate()` refuses to mix it with standard
records; it is not part of the policy-facing benchmark.

## 8. PufferLib / vectorized loading

The registry feeds both consumers: `IWannaDiscoveryEnv(task=…)`
(Gymnasium reference) and `binding_kwargs(task_id)` → numeric kwargs
for `c_src/binding.c` plus `IWG_PACK` / `IWG_LEVEL_FILE` environment
variables (kwargs are numeric-only in the Ocean harness). Vectorized
stepping is demonstrated in `tests/test_discovery_suite.py` for both
accepted task classes (native pack tasks and controlled rooms); the
pack path is generic — a future `iwbtg_original_2007` pack loads
through the identical mechanism with no binding changes. OOD gains the
same treatment the day a K2W task is coverage-approved.

## 9. Exclusions (unchanged from the audit, restated)

7 native exclusions (boss rooms; precision-only rGuyTower,
rGuyLabyrinth, rZelda, the rGuy1 fruit wall; the progression-dependent
orb gate; the no-fabrication placeholder for `iwbtg_original_2007`),
4 controlled exclusions (t07/t15/t16/t19 — timing/observation rooms),
plus the 2 newly flagged controlled tasks (t05/t08) removed from
scoring by their own diagnostics. Full evidence per row in the
manifest and diagnostics directories.
