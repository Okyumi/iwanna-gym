# Importer architecture

The offline pipeline that turns source-game project data into packs the
native runtime steps at millions of frames per second:

```
GameMaker/MMF/source project          (user-provided; never committed —
        ↓                              third_party/SOURCES.md)
source-specific extractor             tools/importers/<name>.py
        ↓
canonical intermediate representation .iwgame.json  (docs/gamepack_format.md)
        ↓
validator/compiler                    iwanna_gym/gamepack/
        ↓
compact native game pack              .iwpack
        ↓
C/PufferLib environment               c_src/iwanna.h + c_src/gamepack/iwpack.h
```

Everything above the last arrow is offline Python. The C runtime parses
the pack exactly once at environment construction; during `step()` there
are no Python callbacks, no allocation, no string lookups, and no
parsing — the native stepping path that existed before packs is
preserved (and still used verbatim for the classic single-room levels
and the procedural/debug rooms).

## CLI

```bash
python -m tools.iwimport inspect  <source_dir>                 # extract + report, never fails on unknowns
python -m tools.iwimport convert  <source_dir> -o g.iwgame.json [--game ID] [--importer NAME]
python -m tools.iwimport validate g.iwgame.json [--allow-unsupported]
python -m tools.iwimport compile  g.iwgame.json -o g.iwpack [--allow-unsupported]
python -m tools.iwimport report   g.iwgame.json                # mapping/provenance report
```

Loading in Python:

```python
env = iwanna_gym.IWannaEnv(pack="g.iwpack", checkpoint_respawn=True)
# or, low level:
c = iwanna_gym.clib.CIWanna.from_pack("g.iwpack")
```

## Unknown and unsupported source semantics

The importer never guesses. Every element ends up in exactly one bucket:

| status | meaning | validate | compile |
|---|---|---|---|
| `exact` | identical semantics | ok | compiled |
| `equivalent` | documented behavioral difference (`notes` required) | ok | compiled |
| `unsupported` | identified, runtime cannot represent it | **error**¹ | **error**¹ |
| `unknown` | importer could not identify it | **error**¹ | **error**¹ |

¹ `--allow-unsupported` turns validation errors into warnings
(inspection mode) and lets `compile` proceed by dropping those elements
**visibly**: the pack metadata lists every dropped element and carries
`"incomplete": true`, and the CLI prints the list. Silent discarding is
a bug by definition; `tests/test_gamepack.py` locks the failure mode in.

The same honesty rule applies at the profile level: a pack declaring a
physics or action profile the runtime does not implement is rejected at
both validation and native load (`physics_profile` is not a suggestion —
see docs/fidelity_contract.md).

## Importers

`tools/importers/` — one module per source format, exposing
`NAME`, `detect(path)`, `extract(path, game_id=None)`:

* **`synthetic`** — the reference extractor for the committed test
  fixture (`tests/fixtures/synthetic_src`, format `synthsrc/1`). The
  fixture is original synthetic content shaped like a generic editor
  export (per-room JSON, px instances, declarative events) so the
  pipeline is exercised end to end without any third-party data:
  two rooms, solid geometry, spikes, a save, a cross-room warp, a moving
  platform (a documented `equivalent` mapping), a region trigger, one
  global progression flag, a flag-opened gate, and a linked room edge.
  A second fixture (`synthetic_src_unknown`) contains an unknown object
  and an unknown event type to test the failure path.
* **`gm82`** — scaffold only (raises `NotImplementedError` with
  pointers): the GM8.2 text-tree importer for renex²-style projects and,
  pending format verification, the IWBTGR 1.5.3 source. Implementing it
  is the next milestone; the audit trail for its sources is
  `third_party/source_manifest.toml`.

### Adding an importer

1. Write `tools/importers/<name>.py` with `NAME`, `VERSION`,
   `detect()`, `extract()` returning a `schema.new_gamepack()` document.
2. Map source objects through an explicit table; everything outside the
   table becomes `unknown` (never skip, never guess). Behavioral
   differences get `equivalent` + `notes`.
3. Fill provenance on every element (`source_room`, `source_object`,
   `source_instance`, `source_event`) and the top-level source checksum.
4. Register the module in `tools/importers/__init__.py`.
5. Give it a fixture and tests. Committed fixtures must be original or
   clearly redistributable (third_party/SOURCES.md).

## Performance protection

`scripts/benchmark_env.py` measures pure-C stepping (random actions
generated inside the C library — no Python or ctypes in the timed loop)
over four protected scenarios: `empty` (entity-free static room),
`trap` (controlled trap room t20_finale), `pack` (the imported synthetic
game pack), `heavy` (1000-entity room). A regression above ~10% on the
entity-free path versus a recorded baseline is a problem requiring
investigation before merge.

Reference numbers (single core, gcc -O2, this repo's sandbox CI box,
best of 3, 2026-08-27):

| scenario | before pack support | after |
|---|---|---|
| empty | 3.70 M steps/s | 3.72 M steps/s |
| trap (t20_finale) | 2.09 M steps/s | 2.18 M steps/s |
| pack (synthetic fixture) | — | 2.89 M steps/s |
| heavy (1000 entities) | 0.070 M steps/s | 0.070 M steps/s |

The pack path adds two predictable branches to `c_step` (edge check +
pending-transition check) and nothing to the inner loops; room switches
are bounded memcpys that occur only on transition frames.

## What this milestone deliberately does not do

No real game content is imported yet (the IWBTGR importer is the next
milestone), no manual recreation of any IWBTG room exists anywhere in
the repo, and difficulty variants / general bosses are representable in
the IR but rejected by the compiler as `unsupported` until the runtime
implements them.
