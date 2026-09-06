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
  screen+hazard-family splits that H4 shows produce large,
  consistent train→holdout drops for every policy (memorization is
  measurable and controlled).
- Failures are repeatable under fixed hidden state (RDR ≈ 1.0 for all
  pilot agents), i.e. the informative-failure structure is present in
  the tasks.

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

1. Witness the 24 pending native tasks (human-play capture is the
   direct path) — the headline suite must be scoreable end to end.
2. Scale the pilot to convergence budgets on real hardware
   (≥64 cores, 10⁸–10⁹ steps, ≥5 seeds) — the pilot's null H1 at
   3–5M steps on 2 cores is uninformative about the hypothesis itself.
3. Agents that can plausibly use failure information: longer-BPTT /
   transformer-XL-style memory, better episodic conditioning than the
   mean-window baseline, and the memory-oracle upper bound run — if
   even the oracle cannot exploit revealed hazards, the task design
   needs revision before any agent claim.
4. The B2 informed-vs-blind scripted probe comparison across all
   native tasks (currently probe-status pending).
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
the framing should not promise one. Revise rather than stop: the two
structural risks surfaced by the pilot — recurrence optimization costs
masking memory effects, and stochastic-retry inflation of S(k) — are
both addressable inside the current contract (report ablation-relative
gains only; add greedy-eval and matched-capacity controls to the
protocol). Stop is not indicated: no evidence contradicts the premise
that the tasks contain exploitable failure information (RDR ≈ 1.0 shows
it is simply unexploited so far).
