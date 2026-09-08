# Discovery benchmark — revised preregistration (v2)

Supersedes the v1 pilot prereg. Written only AFTER the entry gates
cleared: the measurement repair (terminal-event capture, unified
evaluator — `docs/discovery_pilot_report.md`), the observation-matched
informative-failure control (`docs/informative_failure_control.md`), and
learner validation (FF + GRU/BPTT finite-difference gradient checks —
`docs/discovery_training_report.md` §3b). It fixes hypotheses, agents,
controls, splits, budgets, and stop rules BEFORE the scaled run. Nothing
here is executed yet; this is the plan the large experiment will follow.

## Research question

How efficiently can an agent use information revealed by FAILURE to
improve later attempts at the SAME task? Headline content is classic
IWBTG (Remastered today; Original when extracted — kept distinct);
controlled rooms are the laboratory where hypotheses get statistical
power and counterfactual variants.

## Gate status carried in (must hold before launch)

- Measurement: terminal state read before respawn; one evaluator path;
  RDR is a same-room 32px PROXY, not proof of informative failure.
- Positive control (controlled lab): the observation-matched agent solves
  7/7 informative rooms in ~1 death; the memory-erased twin solves 0/7;
  fixed-schedule and attempt-counter controls solve only the one
  coincidentally-aligned room. So the tasks CAN carry exploitable,
  observation-accessible failure information — established without RL.
  This is the necessary premise; whether a LEARNED agent exploits it is
  the open question below.
- Learner: FF and GRU/BPTT gradients FD-checked; advantage normalization,
  update schedule, and counters audited; the recurrent INPUT PROTOCOL is
  a validated spec that this experiment WIRES IN as a separately-reported
  agent (it changes the input dimension).

## Hypotheses (pre-registered, directional where stated)

- **H1 (causal memory).** A recurrent policy that CARRIES hidden state
  across attempt deaths achieves a higher within-task adaptation gain
  (AUC of S(k), and S(k)−S(1)) than the identical policy whose hidden
  state is RESET at every attempt boundary. Primary metric: ablation
  gap in adaptation gain, averaged over tasks, with uncertainty across
  training seeds.
- **H2 (explicit episodic memory).** Adding the bounded death-memory
  feature improves adaptation gain over the observation-only recurrent
  policy. Reported separately from H1.
- **H3 (repeated-death reduction).** Memory reduces the repeated-death
  PROXY relative to the reset ablation. H3 REQUIRES RETRAINING — the
  pilot's deathmem consumed the timeout bug; the pilot H3 is void.
- **H4 (non-trivial splits).** Train→holdout skill drop is large for all
  policies (a necessary, not sufficient, memorization control).

## Agents (all share init where paired; each a distinct, separately reported spec)

1. `ff` — memoryless baseline.
2. `gru_carry` — hidden state carried across attempt deaths, cleared at
   task end. **Trained separately** from its ablation.
3. `gru_reset` — identical architecture and init; hidden state ALSO
   zeroed at every attempt boundary. **Trained separately** (not just an
   eval-time switch), so the comparison includes any optimization cost of
   carrying memory.
4. `gru_carry+proto` / `gru_reset+proto` — as above, plus the permitted
   input protocol (prev-action one-hot, clipped prev-reward, observed
   attempt-boundary flag; `input_protocol.py`). The extra inputs are
   IDENTICAL between the carry and reset arms (only the recurrent cut
   differs) and carry NO hazard identities or hidden task parameters.
   Reported as a separate agent family — never pooled with the obs-only
   agents.
5. `deathmem` — bounded episodic memory (mean of last-N pre-death
   observations + death counter), cleared at task reset.
6. `gru_oracle` — privileged observations. ORACLE upper bound, tagged in
   every output, refused the headline label; if even the oracle cannot
   exploit revealed hazards, the task design is revised before any agent
   claim.

## Same-checkpoint cross-attempt memory evaluations (diagnostic)

For each trained `gru_carry` checkpoint, evaluate three memory regimes at
FIXED weights (no retraining):

- **intact** — hidden state carried across deaths (as trained);
- **erased** — hidden state zeroed at each attempt boundary;
- **shuffled** — at each boundary the carried hidden state is replaced by
  a hidden state sampled from ANOTHER attempt/env.

Shuffle is a DIAGNOSTIC, not a clean ablation: it can inject
distribution shift (an off-manifold hidden state), so a drop under
shuffle is consistent with either "memory content mattered" OR "the
policy is brittle to unfamiliar hidden states". Reported with that
caveat; the causal claim rests on the **separately-trained** carry-vs-
reset comparison (H1), with intact/erased/shuffled as supporting texture.

## Controls

- **Stochastic-retry control.** For every S(k) reported, include the
  memoryless `ff` policy under the SAME K attempts: stochastic policies
  inflate S(k) purely by re-sampling. Headline adaptation is the gap
  ABOVE this retry baseline (and above `gru_reset`), never raw S(k).
- **Informative-failure controls (controlled lab).** The four-arm
  scripted control (obs_memory / erased / fixed / attempt_counter) on the
  `hidden_spike_*` family, plus new counterfactual variants
  (disarm / relocate / retime the hidden trap) confirming the learned
  gain tracks the hidden state.
- **Difficulty / solvability.** Every scored task has a replayed
  completion witness (solvable) and a blind-policy diagnostic (not
  trivially solvable without adaptation); tasks failing either are
  excluded and kept visible as pending, never softened.
- **Anti-leakage.** Observable obs only for headline agents; paired
  make_killer/make_harmless and dormant/armed tests assert no hidden
  field leaks; the input protocol is checked to carry no hazard identity.

## Splits and uncertainty

- Screen + hazard-family held-out splits (H4). Report train and holdout
  separately; never pool.
- Uncertainty: >= 5 independent training seeds per agent; report the seed
  distribution of the H1 gap (mean, spread, sign consistency), not a
  single run. A gap whose sign flips across seeds is reported as null.

## Training budgets — from evidence, not a round number

The pilot null H1 sat at 2–5M env steps on 2 cores, where S(k) curves
had NOT plateaued (adaptation gain still ~0). So the evidence says the
budget must be larger AND selected by a plateau criterion, not by an
arbitrary 10⁸–10⁹ target:

- **Throughput evidence** (`docs/discovery_training_report.md`): sim
  ~120k SPS (controlled) and end-to-end ~15–20k SPS recurrent on 2 cores;
  ~10× cores makes ~50M steps/seed a ~1-hour wall-clock run.
- **Stop rule.** Train to a plateau: early-stop when holdout adaptation
  gain fails to improve by > 0.01 over a 5M-step window, with an INITIAL
  ceiling of 50M steps/seed (justified by the throughput above). Raise
  the ceiling ONLY if the learning curve is still rising at the cap, and
  record the revised ceiling. Report the actual curves; do not extrapolate
  synthetic-room throughput to native rooms (budget native runs from
  native throughput).

## Execution order (corrected — do NOT jump to multi-seed)

The scaled multi-seed study is LAST, not next. Staged order:

1. **Real PufferLib smoke run** on a capable machine — one controlled +
   one witnessed native task — verifying collection/updates, finite
   losses + changing params, termination/truncation + value bootstrap,
   checkpoint reload + shared-evaluator eval, and end-to-end throughput
   (`scripts/puffer_launch.py` → `puffer_smoke.py` → `puffer_verify.py`).
   **Blocking wiring first** (surfaced by `puffer_verify.py`): (a) expose
   `task_exhausted` as a truncation signal so value bootstraps on
   exhausted tasks; (b) wire the reset-memory (`gru_reset`) ablation
   (zero recurrent state at attempt boundaries — `gru_carry` already
   comes free from the task-end terminal); (c) wire the `input_protocol`
   extras into the policy for the `+proto` agents. Until (a)–(c) land and
   the smoke passes, the ablation cannot run correctly.
2. **Small learning diagnostic** — a few-million-step run on the
   controlled suite (incl. the `informative` rooms) to confirm the
   learning curve MOVES and to locate the plateau region that sets the
   budget. Not a hypothesis test; a scale/behavior check.
3. **Preregistered multi-seed study** (H1–H4) — only after 1–2 pass,
   with ≥5 seeds and the plateau stop rule below.

## Primary analysis and decision

Confirm H1 iff the separately-trained carry-vs-reset adaptation-gain gap
is positive with consistent sign across >= 5 seeds AND exceeds the
stochastic-retry and reset baselines. H2/H3 reported independently.
Negative or sign-flipping results are reported as such — the benchmark
paper stands on the environment, the controls, and an honest map of what
learned agents do and do not achieve.
