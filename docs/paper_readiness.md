# Paper readiness assessment

Written after the pre-registered pilot
([discovery_pilot_report.md](discovery_pilot_report.md), 2026-09-05).
Scope discipline: every claim below is tagged supported / unsupported
by current evidence.

## Supported claims (evidence in the repo today)

- A deterministic, source-exact I-Wanna benchmark environment exists
  with verified physics and content fidelity (frozen `iwbtgr_1_5_3_v1`
  pack: 20/20 room audits, 24/24 differential checks, classified
  deviation ledger) and millions-of-steps/s native throughput measured
  on the real workload, not tiles (41k–3.6M steps/s by room class;
  3.3× the reference Gymnasium path on the same exact-game task).
- The multi-attempt discovery task formalization is implemented in the
  native core with proven properties: attempt/task boundary semantics,
  fixed per-task hidden state, deterministic replay, leak-free
  observation modes (paired anti-leakage tests), and a causal
  memory-vs-reset experimental pair that is parameter- and
  interaction-identical and differs only at the death boundary
  (bit-identical-until-first-death test).
- The suite machinery works as designed: audited task selection with
  committed evidence, completion witnesses, blind-policy diagnostics
  that removed two tasks for insufficient hidden information, and
  screen+hazard-family splits that H4 shows produce large, consistent
  train→holdout drops for every policy. This demonstrates the splits
  are NON-TRIVIAL — training-task skill does not transfer — which is a
  NECESSARY condition for isolating memorization, but **holdout
  collapse alone does not prove memorization is isolated**: it is also
  consistent with the held-out tasks simply being harder or
  out-of-distribution for the trained features. Proving isolation
  additionally needs held-out performance that a within-task
  adaptation signal (present under memory, absent under the ablation)
  can move — which the pilot has not yet shown.
- Deaths recur under fixed hidden state (corrected repeated-death rate
  ~0.93–0.99; the pre-repair RDR ≈ 1.0 is superseded — see the
  measurement-repair note). RDR is a spatial proxy for "died at the
  same hazard again", not by itself proof of informative failure.
- **The tasks contain EXPLOITABLE, OBSERVATION-ACCESSIBLE failure
  information (observation-matched scripted control, no RL).** On the
  ambiguous-hidden-state controlled rooms (`levels/informative/`), where
  the trap is INVISIBLE in the observation until it kills, an agent
  conditioning only on its OWN observed failure location solves **7 of
  7** rooms in ~1 death; the byte-identical memory-erased twin solves
  **0 of 7**; and BOTH a fixed blind schedule and an attempt-counter
  control solve only the single room whose trap coincides with their
  fixed guess (`iwanna_gym/discovery/informative.py`,
  `build/informative_control/results.json`,
  `tests/test_informative_control.py`,
  `docs/informative_failure_control.md`). The claim is **efficiency, not
  uniqueness**: a blind `location_search` enumerator ALSO solves all 7
  rooms but pays ~4.3 deaths on average vs the memory agent's 1.0, and a
  continuous-jump strategy solves 0/7 — so the observed failure location
  buys a ~4× interaction-cost reduction, and the necessary contrast
  (identical agent, memory the only change: 7/7 vs 0/7) shows that memory
  is what enables the efficient solve. It uses no privileged fields (the
  earlier `probes.py` agent, which read the exact terminal snapshot
  `term_x`/`term_room`, is retained only as a labeled PRIVILEGED ORACLE
  upper bound). Scope: this shows the failure history CARRIES usable
  information an agent CAN exploit more efficiently; it does NOT claim a
  *learned* agent will — that is the open question the scaled experiment
  (`docs/discovery_prereg_v2.md`) poses.

## Unsupported claims (do NOT write these today)

- "Cross-attempt memory improves discovery-task performance": the
  pre-registered causal comparison is NULL at pilot scale
  (AUC gap +0.008 ± 0.159, sign flips across seeds).
- "Explicit death memory reduces repeated deaths": refuted in
  direction at pilot scale (H3).
- Anything about the original 2007 IWBTG (unextracted; feasibility
  gated), about IWBTGR-native learning beyond one task (24 native
  tasks await witnesses; the one active native task sits at 0.000 for
  every pilot agent), or about K2 WARPED (zero coverage-approved
  tasks).
- Any success-by-attempt improvement read as adaptation without the
  ablation control (stochastic retry inflates S(k) for memoryless
  policies).

## Exact role of each content family

- **`iwbtg_original_2007`**: future headline content, currently a
  registration + external-extraction gate; no tasks, no claims.
- **`iwbtgr_1_5_3` (Remastered — always labeled as such, never "the
  original")**: the source-native headline suite; 25 audited tasks, 1
  active today; its fidelity chain (source → pack → task) is the
  paper's environment contribution.
- **Controlled research rooms**: the causal laboratory — where
  hypotheses get statistical power and counterfactual variants; never
  presented as IWBTG content.
- **K2 WARPED**: OOD transfer only, gated on its dynamics milestone;
  never pooled into headline numbers.

## Remaining experiments for a conference submission

1. Witness the 24 pending native tasks — human-play capture is the
   direct path. Automated beam-search witnessing did NOT find a solution
   for a diverse sample within a bounded in-sandbox budget (e.g. the
   game's first room, 150s → pending), so these remain pending_witness,
   kept visible; the headline suite is not yet scoreable end to end.
2. Scale the pilot to convergence budgets on real hardware
   (≥64 cores, 10⁸–10⁹ steps, ≥5 seeds) — the pilot's null H1 at
   3–5M steps on 2 cores is uninformative about the hypothesis itself.
3. Agents that can plausibly use failure information: longer-BPTT /
   transformer-XL-style memory, better episodic conditioning than the
   mean-window baseline, and the memory-oracle upper bound run — if
   even the oracle cannot exploit revealed hazards, the task design
   needs revision before any agent claim.
4. The informed-vs-blind scripted probe across native tasks.
   `chalice_hall` is a PLAUSIBLE candidate, not a dead one: its 0-death
   witness proves solvability via one clean path but not that failure is
   uninformative — its hazards are `maskless_until_armed` /
   `flickering_mask` / `arming_cascade`, and deviating from the witnessed
   path is lethal at well-defined arming locations (verified). An
   initially-uninformed agent would die on the cascade; whether that
   failure is exploitable depends on the observability of the arming
   state (open, testable). A proper probe needs an uninformed agent that
   reaches and dies there (human witness or navigation policy) — see
   `docs/native_witness_workflow.md`.
5. Counterfactual variants (disarm/relocate/retime) on controlled
   tasks for the causal "the agent used the death" analysis.
6. IWBTGR held-out native transfer once witnesses exist (H4's native
   version).

## Recommendation

**Proceed — with the environment/benchmark as the paper's core
contribution, and with the memory science gated on scale.** The
evidence supports a benchmark paper (exact-game environment + audited
discovery suite + causal evaluation protocol + demonstrated
anti-memorization controls + a documented null at pilot scale as the
open challenge). It does not support an algorithmic-finding paper, and
the framing should not promise one. Revise rather than stop: the
structural risks surfaced so far — recurrence optimization costs
masking memory effects, stochastic-retry inflation of S(k), and (from
the measurement audit) evaluation that must read terminal state before
respawn — are all addressable inside the current contract (report
ablation-relative gains only; add greedy-eval and matched-capacity
controls; the terminal-event capture is now fixed and tested). Stop is
not indicated. The premise that the tasks contain *exploitable,
observation-accessible* failure information is now **demonstrated in the
controlled laboratory** by the observation-matched four-arm control
(7/7 vs 0/7, confounds ruled out) — not asserted from RDR. What remains
open is the LEARNED-agent question: whether a trained policy discovers
and uses that structure, and whether the effect holds on native IWBTG
content. The honest status is unchanged in spirit: the benchmark's
machinery is sound, its controls are real and now include a passing
positive control, and whether *learned* agents exploit the failure
structure is the empirical question the scaled experiment
(`docs/discovery_prereg_v2.md`) poses. Content coverage — Original vs
Remastered kept distinct, extraction/witness/scoring status per family —
is tabulated in `docs/coverage_table.md`.
