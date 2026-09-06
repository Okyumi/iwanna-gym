# Real PufferLib training integration

The discovery benchmark trains through **PufferLib Ocean**, pinned to

    repo    https://github.com/PufferAI/PufferLib
    version 4.0.0
    commit  42f70d6932c30ac977736f861006809c50168ba9

This is the maintained, GPU-capable learner path (CleanRL-style PPO in
torch). The custom NumPy PPO of the earlier pilot is retained ONLY as
the reference/parity implementation (`iwanna_gym/discovery/baselines.py`)
and for reproducing the legacy pilot numbers; it is not the training
path this milestone establishes.

## What is in this repo

- `c_src/puffer/binding.c` + `c_src/puffer/iwanna_puffer.h`: the real
  PufferLib **4.0.0** Ocean binding. 4.0.0 changed the Ocean API (it now
  uses `vecenv.h`, `Dict* kwargs`, `dict_get`/`dict_set`, float
  `actions`/`terminals`, and OBS/ACT macros); the retired
  `c_src/binding.c` targeted the old `env_binding.h` API and does not
  build against 4.0.0. The adapter wraps the unmodified IWanna core
  (which uses `int` actions and `uint8` terminals) and translates the
  buffers each frame, so the ctypes/`CVecIWanna` reference path is
  untouched. It compiles cleanly against the pinned `vecenv.h`
  (`tests/test_pufferlib_binding.py`,
  `gcc -fsyntax-only -fopenmp -I <PufferLib>/src -Ic_src/puffer
  c_src/puffer/binding.c`).
- `config/iwanna_puffer.ini`: the 4.0.0 config. Its `[env]` keys are
  exactly what `binding.c` reads via `dict_get`; the discovery registry
  (`iwanna_gym.discovery.binding_kwargs(task_id)`) emits those same
  numeric kwargs plus the file-path env vars for any registered task.
- `scripts/setup_pufferlib.sh`: clones the pinned PufferLib, stages the
  iwanna env into `ocean/iwanna/`, installs the config, and prints the
  build/train commands.
- `scripts/puffer_smoke.py`: self-verifying smoke harness (below).

## Reproducible run (on a training-capable machine)

Requires torch + PufferLib 4.0.0 installed and a C toolchain with
OpenMP. Not runnable in the sandbox this was authored in (no torch;
pypi blocked) — see "Blocked here".

```bash
# stage the env into the pinned PufferLib checkout
bash scripts/setup_pufferlib.sh $HOME/PufferLib

# --- controlled research room (fast) ---
export IWG_LEVEL_FILE=$PWD/iwanna_gym/levels/traps/t06_crusher.txt
cd $HOME/PufferLib
puffer build iwanna
puffer train iwanna --train.total-timesteps 2000000

# --- native source-derived task (needs a locally-built pack) ---
# build the pack from a local IWBTGR source checkout (never committed):
python -m iwanna_gym.games.iwbtgr_1_5_3 build <source_checkout>
# emit the task's numeric kwargs + IWG_PACK:
python -c 'import iwanna_gym.discovery as d, json; \
  k, e = d.binding_kwargs("disc.iwbtgr_1_5_3.rGuyFortress1.chalice_hall"); \
  print(json.dumps(k)); print(e)'
# set IWG_PACK to the printed path and apply the printed [env] overrides
# (use_pack=1, task_start_*, task_goal_*) in config/iwanna.ini, then:
puffer build iwanna && puffer train iwanna
```

Observation mode is fixed by `obs_mode` in `[env]`: **1 = observable**
(headline), **0 = privileged** (oracle upper bound — forbidden for
headline results). Pixel observations are NOT supported for native
packs; offline visualization uses the separate renderer
(`iwanna_gym.discovery.viz`), never the training obs path.

## Blocked in the authoring sandbox (milestone status: UNVERIFIED here)

`torch` is not importable and cannot be installed (pypi returns 403;
`pip install` finds no wheels, even for `numpy`). PufferLib 4.0.0 pulls
torch, so a real `puffer train` run cannot execute in this environment.
`scripts/puffer_smoke.py` therefore writes
`build/pufferlib_smoke/status.json` with `verified:false`, the precise
blocker, and the exact external command above; on a torch-capable
machine the same script runs the real short train + eval and records
throughput.

What IS verified here, torch-free:
- the 4.0.0 binding compiles against the pinned PufferLib headers;
- every `[env]` kwarg the binding reads is present in the config and is
  emitted by the registry for both a controlled and a native task;
- simulation-only throughput on controlled and native workloads
  (`scripts/bench_discovery_vec.py`);
- task/attempt termination, recurrent-state resets, terminal
  observations, heterogeneous batching, and deterministic
  matched-action parity with the reference env
  (`tests/test_discovery_runtime.py`, `test_discovery_training.py`,
  `test_terminal_events.py`);
- the observable-vector observation contract — offscreen/inactive
  entities, invisible/unarmed hazards, dormant state, camera visibility
  (`tests/test_observation_contract.py`).

## Throughput methodology

Report simulation-only steps/s (pure C stepping, no learner) and
end-to-end learner steps/s (with the torch update) SEPARATELY, and
never extrapolate synthetic-room speed to classic games. Sim-only
numbers by workload are in `docs/discovery_training_report.md`
(`scripts/bench_discovery_vec.py`): controlled rooms are ~orders of
magnitude faster than 1000+-instance IWBTGR rooms, so the two are
always reported per workload with hardware, batch size, policy, obs
mode, and versions. End-to-end PufferLib learner throughput is recorded
by `scripts/puffer_smoke.py` on the machine that runs it.

## Learner validation and the reference implementation

The reference NumPy PPO's hand-written gradients are checked against
finite differences (`tests/test_discovery_training.py::
test_ff_policy_gradient_matches_finite_differences`); its update
counting, GAE, and memory-boundary handling are unit-tested. PufferLib
supplies its own maintained, separately-tested PPO; when comparing the
two, differences in optimizer, minibatching, and normalization are
expected and are documented per run rather than treated as bugs. The
legacy pilot results (reference learner) remain reproducible via
`scripts/run_pilot.py` and the committed configs.
