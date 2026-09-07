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

7 rooms, K=25 attempts, H=400 frames, observable_vector, deterministic:

| arm | rooms solved | mean deaths-to-success |
|---|---|---|
| `obs_memory` | **7 / 7** | **1.0** |
| `erased` | 0 / 7 | — (25 deaths, no success) |
| `fixed` | 1 / 7 | 0.0 (the one room whose trap = the guess) |
| `attempt_counter` | 1 / 7 | 1.0 (only the aligned room) |

6 of 7 rooms **separate cleanly**: `obs_memory` solves, `erased` fails,
and BOTH blind controls fail. The 7th (`hidden_spike_3`, trap at the room
center) is solved by the blind arms too because their fixed guess is the
center — correctly excluded from `separates`.

**Interpretation, scoped.** The observed failure location is *sufficient*
for a scripted agent to solve every room in a single death; removing that
memory (erased twin) removes all success; and neither a fixed action
sequence nor an attempt counter reproduces it (each clears only the
coincidentally-aligned room). This establishes that the tasks contain
**exploitable, observation-accessible failure information** — without any
converged training. It does **not** claim that a *learned* agent will
discover this policy; that remains the open empirical question for the
scaled experiment. Repeatability alone is excluded as evidence: the erased
twin fails just as reproducibly, so the reported signal is success **and**
the death-cost gap (1 vs 25), not repetition.
