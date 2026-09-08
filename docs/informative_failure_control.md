# Informative-failure positive control — audit and observation-matched result

This documents (1) an audit of the original scripted failure-memory probe
(`iwanna_gym/discovery/probes.py`), (2) the observation-matched redesign
that removes its privileged input and its non-ambiguous tasks
(`iwanna_gym/discovery/informative.py`), and (3) the four-arm result that
isolates *the observed failure location* as the cause of the improvement.

## 1. Audit of the original probe (`FailureMemoryAgent`)

**Every input it consumes.** `observe()` reads `info["attempt_ended"]`,
`info["attempt_event"]`, `info["term_x"]`, `info["term_room"]`. `act()`
reads `info["room"]`, `info["x"]`, and its own recorded deaths.

**Finding — the terminal coordinate is privileged.** `term_x`/`term_room`
come from the terminal-event snapshot captured in C *before* respawn. They
are **evaluator-facing** (the milestone-18 repair added them precisely so
the evaluator could read the pre-respawn state); they are **not** in the
policy observation. The observable vector carries `o[0] = 2x/W - 1` (a
normalized player x) and no room index. Two concrete gaps:

- **Precision / staleness.** On the fatal step the environment auto-resets,
  so the observation an agent receives on the boundary step shows the
  *respawn* position, not the death position. The last *pre-death*
  observation is one frame stale. Measured on `hidden_spike_2`: exact
  `term_x = 327.0` vs the agent's own last observed x `= 324.0` — a ~3px
  gap. Small here, but it is information the observation does not contain.
- **Room index.** `term_room` is not encoded anywhere in the observation.

**Finding — the original tasks are not "initially ambiguous".** The
t01..t20 rooms use hazards that are DRAWN as deadly in observable mode
(`iw_type_deadly_appearance`), so a good observation-only policy can see
the hazard without dying. Repeatability of deaths there is a spatial proxy,
not proof that *failure* (as opposed to *vision*) carried the information.

**Finding — seeds are not configurations.** The controlled rooms are
deterministic; `task_seed` seeds an RNG stream that these rooms do not
consume, so "reproducible across 3 seeds" was one configuration run three
times. Verified: `hidden_spike_2` yields an identical outcome (success, 1
death, learned x = 324.0) for `task_seed ∈ {1, 7, 42, 1000}`. **Distinct
configurations are distinct rooms**, so hidden state must be varied across
rooms — which is what the new family does.

The original probe is retained, explicitly relabeled as a **privileged
oracle upper bound** (it shows an agent *with* exact death coordinates can
exploit them — a strictly weaker claim than the observation-matched one).

## 2. Observation-matched design (`informative.py` + informative rooms)

**Rooms** (`scripts/make_informative_rooms.py`, `levels/informative/`).
A flat S→G corridor. At a hidden column `Xt` an INVISIBLE `enter_region`
band at floor level spawns a lethal spike ON a grounded player. The band
and spike are absent from the observation until the spike is spawned
(offscreen/unspawned entities are excluded from the observable vector),
so `Xt` is **initially ambiguous** — the entity block is all-zero on the
approach (asserted by test). The only way to learn `Xt` is to die there
(an OBSERVABLE failure). Being AIRBORNE over the band (a full, well-timed
jump) avoids the trigger; a grounded run into it dies. `Xt` varies across
7 rooms {6,8,10,12,14,16,18} so no fixed action sequence clears them all.
Source hazards/physics/checkpoints are unchanged — this is a controlled
research family, never presented as IWBTG content.

**Agents** condition ONLY on observed facts: `obs[0]` (player x), `obs[5]`
(on-ground), the success flag, and the permitted attempt-boundary flag.
A memory arm records, as its death location, its OWN last observed x
before a failed attempt — never `term_x`. Four arms:

| arm | what it does | isolates |
|---|---|---|
| `obs_memory` | jump over the OBSERVED death column | headline |
| `erased` | same agent, memory cut each attempt (never jumps) | memory is necessary |
| `fixed` | one blind program, jump at a fixed guessed column | a single sequence can't solve all |
| `attempt_counter` | jump on attempt ≥ 2 like `obs_memory`, but at a FIXED guessed column (not the observed death) | the OBSERVED LOCATION vs the attempt counter |

## 3. Result (`build/informative_control/results.json`)

7 rooms, K=25 attempts, H=400 frames, observable_vector, deterministic.
Six arms — the memory agent, its erased twin, two blind controls, and two
COMPETING strategies (a continuous jumper and an attempt-based location
search) added so the interpretation is bounded, not inflated:

| arm | rooms solved | mean deaths-to-success |
|---|---|---|
| `obs_memory` (headline) | **7 / 7** | **1.0** |
| `erased` (same agent, memory cut) | 0 / 7 | — (no success) |
| `fixed` (one blind program) | 1 / 7 | 0.0 (trap = the guess) |
| `attempt_counter` (jump-on-≥2, fixed column) | 1 / 7 | 1.0 (aligned room) |
| `continuous_jump` (maximally airborne, no memory) | 0 / 7 | — |
| `location_search` (enumerate jump column by attempt) | **7 / 7** | **4.3** |

**Interpretation — efficiency, not uniqueness (bounded).** The headline
claim is NOT "only the memory agent can solve these". It is that the
memory agent uses the OBSERVED failure location to solve with MINIMAL
interaction cost. Two facts fix the interpretation:

1. **Necessary contrast (identical agent).** `obs_memory` solves 7/7;
   its byte-identical memory-erased twin solves 0/7. The only difference
   is whether the observed death location is remembered across attempts —
   so that memory is what enables the solve. All 7 rooms separate on this
   contrast (`separates_vs_erased`).
2. **The observed location buys efficiency, not a capability others
   lack.** A blind `location_search` enumerator ALSO solves all 7 rooms —
   by trying a different fixed jump column each attempt — but pays **~4.3
   deaths** on average versus the memory agent's **1.0**. So the honest
   claim is a ~4× interaction-cost reduction from using the observed
   failure, not that the failure information is strictly required to ever
   succeed. Meanwhile a `continuous_jump` strategy (as airborne as the
   physics allow, no location) clears **0/7** — constant jumping is not a
   shortcut — and a single `fixed`/`attempt_counter` column clears only
   the coincidentally-aligned room.

This establishes that the tasks contain **exploitable,
observation-accessible failure information whose use is measurably more
efficient** — without any converged training. It does **not** claim a
*learned* agent will discover this policy; that is the open question for
the scaled experiment. Repeatability alone is excluded as evidence (the
erased twin fails just as reproducibly): the reported signals are the
memory-vs-erased separation AND the death-cost gap (1.0 vs 4.3), not
repetition.

## 3a. Are the scripted agent's signals available to the learner?

The `obs_memory` agent reads only `obs[0]` (player x) and `obs[5]`
(on-ground) — both inside the observation vector — plus the success flag
and the attempt-boundary flag (`input_protocol`, a permitted observed
input). Every per-step signal it uses is therefore available to the RL
learner too. The one thing it additionally does is RETAIN the death
location across attempts; the learner has no free channel for that — it
must retain it through recurrent hidden state (`gru_carry`) or the
explicit `deathmem` feature. That retention is exactly the capability
H1/H2 test, so the scripted control does not hand the learner anything the
learner cannot in principle compute; it shows the information is present
and useful, and leaves "does a trained net actually retain and use it" as
the open question.
