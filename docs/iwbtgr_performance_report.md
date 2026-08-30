# iwbtgr_1_5_3_v1 performance report

Recorded 2026-08-30 on x86_64 / Python 3.11.15 (single core, shared cloud container — treat absolute numbers as ±20% and compare within this table).

Method: best-of-3 per scenario; steps generated and consumed inside the C library (`iw_bench`) with the STRUCTURED observation computed every step — this is the headless training path, and the speed claim of record. The renderer is never in the loop except in the explicitly-labeled pixel row. Reproduce: `python scripts/benchmark_freeze.py`.

| scenario | steps/s (structured obs, headless) |
|---|---|
| static procedural (legacy `flat`) | 1,063,987 |
| event-heavy controlled (`t20_finale`) | 1,303,584 |
| exact ordinary room (rGuy1) | 47,178 |
| exact entity-heavy (rGuyFortress2) | 25,319 |
| boss room (rKraidgiefBoss) | 42,078 |
| boss room (rDraculaBoss) | 1,508,529 |

Boss rows run from the room spawn under random actions — the training-from-scratch condition; a cutscene-frozen player steps very cheaply (rDraculaBoss). With the fights ARMED by a scripted driver, `scripts/bench_boss.py` measures ~460-480k steps/s (MechaBirdo arena) and ~40k steps/s (Kraidgief, the heaviest room in the game), stable vs the pre-boss baseline within noise.

## Parallel environments (round-robin serial vectorization)

PufferLib is not installable in the build sandbox (no PyPI); this measures the same serial vectorization pattern its default vectorizer drives — one Python loop stepping K C environments. Per-step Python dispatch dominates at K=1 and amortizes as K grows.

| K envs | aggregate steps/s |
|---|---|
| 1 | 46,170 |
| 8 | 62,790 |
| 64 | 69,227 |
| 256 | 70,503 |

## Pixel observations (renderer in the loop)

| scenario | steps/s (RGB frames) |
|---|---|
| t20_finale via PixelObsWrapper | 4,714 |

The paper's speed claim must cite the structured-observation headless rows (and the parallel table for throughput scaling), never the pixel row: pixel rendering is a Python-side convenience wrapper, not the training path.
