# Native task witnessing — human-play recording + deterministic replay

Completion witnesses make a native (Remastered) task scoreable. A witness
is action integers only (metadata-safe to commit); it never contains game
content. Source mechanics are NEVER modified to make a task pass.

## Record → verify workflow

1. **Record a human playthrough** (on a machine with a display + pygame):

       pip install pygame
       PYTHONPATH=. python scripts/record_human_witness.py <task_id> --task-seed 1

   Controls: ←/→ move, ↑/Space jump (tap again in air to double-jump),
   Shift shoot, Esc quit. On task success the recorded actions are handed
   to `witness.write_witness`, which REPLAYS them deterministically and
   writes `manifests/discovery/witnesses/<task_id>.json` only if the
   replay also reaches the goal.

2. **Verify all witnesses replay** (deterministic; run in CI and here):

       PYTHONPATH=. python scripts/verify_witnesses.py

   Exit 0 iff every committed witness replays to success. All 17 current
   witnesses (incl. the native `chalice_hall`) pass after the
   measurement repair.

Because the env is deterministic from `(task_seed, action sequence)`, the
recorded stream is a reproducible witness: anyone can replay it to the same
outcome without the human or a display.

## Small diverse batch to record next

Chosen for distinct source rooms AND distinct hazard mechanics (so the
witnessed set exercises varied dynamics), newest-diverse first:

| task_id | room | hazard families |
|---|---|---|
| `disc.iwbtgr_1_5_3.rGuy1.first_screen` | rGuy1 | first_room_gotcha, trigger_region |
| `disc.iwbtgr_1_5_3.rGraveyard.gravetrap_row` | rGraveyard | touch_armed_delayed_kill, invisible_killer, rises_toward_player |
| `disc.iwbtgr_1_5_3.rGuyRoad.bulletbill_strip` | rGuyRoad | static_until_cart_trigger, invisible_decart_strip |
| `disc.iwbtgr_1_5_3.rMetroid.skwee_gallery` | rMetroid | hanging_diver |
| `disc.iwbtgr_1_5_3.rMegaman.quicklaser_gauntlet` | rMegaman | timed_laser_schedule |

Exact commands:

    for t in disc.iwbtgr_1_5_3.rGuy1.first_screen \
             disc.iwbtgr_1_5_3.rGraveyard.gravetrap_row \
             disc.iwbtgr_1_5_3.rGuyRoad.bulletbill_strip \
             disc.iwbtgr_1_5_3.rMetroid.skwee_gallery \
             disc.iwbtgr_1_5_3.rMegaman.quicklaser_gauntlet; do
        PYTHONPATH=. python scripts/record_human_witness.py "$t" --task-seed 1
    done
    PYTHONPATH=. python scripts/verify_witnesses.py

## Automated witnessing — recorded attempts (NOT a feasibility verdict)

`build/native_witness/automated_attempts.json` records the automated
beam-search attempts. Beam search found no zero-death solution for the
sampled precision rooms within a bounded in-sandbox budget (e.g.
`rGuy1.first_screen`, beam 16 / depth 44 / 150 s → pending). **This is a
compute/budget observation, not a proof that witnessing is infeasible** —
human play is the direct path, and these rooms are solved by humans
routinely. The 24 pending native tasks stay `pending_witness`, visible in
`docs/coverage_table.md`, until recorded.

## chalice_hall is NOT a dead informed-vs-blind candidate

Its existing witness completes with 0 deaths, which proves solvability via
one clean path — it does NOT prove failure is uninformative. chalice_hall's
hazards are `maskless_until_armed`, `flickering_mask`, `arming_cascade`:
initially-ambiguous, arm-on-trigger hazards. Deviating from the witnessed
path is lethal at well-defined locations (verified: idling after 60% of the
path dies at ~(480, 448); running dies at ~(534, 443) — distinct arming
deaths near frame 275). So an initially-UNINFORMED agent would die on the
arming cascade, and the death location is well-defined. Whether that
failure is USEFUL depends on how much of the arming state the observation
reveals (maskless = invisible until armed, like the controlled invisible
traps) — an open, testable informed-vs-blind question, not a task to
dismiss. A proper probe needs an uninformed agent that reaches and dies on
the cascade (the human witness above, or a navigation policy), then
compares informed vs memory-erased runs — the same design as the
controlled `informative` control, on native content.
