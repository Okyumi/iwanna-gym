# Original IWBTG direct-MFA extraction — feasibility gate

Milestone: mfa2pack feasibility spike (2026-09-03).
Scope: can CTFAK 2.0 extract the canonical `iwbtgbeta(fs).mfa` into an
auditable, source-derived inventory? This is a **parser feasibility
decision plus inventory machinery** — not the gameplay port. No
"imported" or "exact" claim is made or implied by anything below.

## 1. Canonical source and the registration gate

The only accepted input is the author-published file:

| field | pinned value |
|---|---|
| filename | `iwbtgbeta(fs).mfa` |
| URL | `https://kayin.moe/iwbtg/source/iwbtgbeta(fs).mfa` |
| size | 85,300,282 bytes |
| SHA-256 | `c41928c4e6599b3535c7a1d0d4b0df4da6068184e037a899af4282b460678f76` |

Registration (added in commit `108ce0c`, `tools/iwimport/source_registry.py`):

```
python -m tools.iwimport register-iwbtg '/path/to/iwbtgbeta(fs).mfa'
```

The command refuses any filename, size, or SHA-256 mismatch and writes a
gitignored local record (`build/source_registry/iwbtg_original_2007.json`).
A mirror is acceptable **only** when its bytes hash to the pinned SHA-256
exactly. Every downstream entry point re-checks the record *and* re-hashes
the file (`require_registered_source`, `tools/importers/iwbtg_mfa/ctfak_runner.py`)
before touching the `.mfa`. The `.mfa`, extracted assets, and any other
copyrighted game content are never committed or redistributed.

**Registration status in this environment: BLOCKED (blocker A, §7).**
The sandbox cannot reach `kayin.moe` (or the Google Drive mirror), so no
byte-verified copy exists here and the positive path of the registration
command has not been run against the real file. The negative paths
(mismatch refusal, forged-record refusal, re-hash refusal) are covered by
tests (`tests/test_source_registry.py`, `tests/test_mfa2pack_spike.py`).

## 2. Pinned CTFAK revision

| field | value |
|---|---|
| repository | <https://github.com/CTFAK/CTFAK2.0> |
| branch / line | `master` — the README-recommended **CTFAK 2.2** line (the `CTFAK-2.3` branch is explicitly marked unstable/WIP by the maintainers) |
| pinned commit | `f38ba7951f5fa9d714dc5d97772882ea6aa61717` |
| license | **AGPL-3.0** |
| project status | archived (read-only) — the pin is therefore stable |
| runtime | .NET 6 (all csproj target `net6.0-windows`); no release tags exist, so there are **no prebuilt binaries** — it must be built from source |

**License boundary (hard rule).** This repository is MIT. CTFAK is AGPL.
CTFAK code is never vendored, copied, or linked into this repo. It runs
as a **separate process** from a user-managed external checkout
(`IWG_CTFAK_DIR`, always outside the repo). `resolve_ctfak()` verifies
the checkout is at the pinned commit before constructing any invocation.
The InventoryDump plugin (§4) is itself a CTFAK plugin and therefore an
AGPL derivative: it lives and is published in its own external AGPL
repository when first built, never here. This repo contains only the
*consumer* of its JSON output plus the documented command line.

## 3. Reproducible install and invocation

Windows (the upstream-supported path):

```
git clone https://github.com/CTFAK/CTFAK2.0 %USERPROFILE%\ctfak2
cd %USERPROFILE%\ctfak2
git checkout f38ba7951f5fa9d714dc5d97772882ea6aa61717
:: requires the .NET 6 SDK + Desktop Runtime
dotnet build -c Release
:: add the external AGPL InventoryDump plugin to Plugins/, rebuild, then:
set IWG_CTFAK_DIR=%USERPROFILE%\ctfak2
python -m tools.iwimport mfa-inventory "path\to\iwbtgbeta(fs).mfa" --run-ctfak
```

Linux: the projects target `net6.0-windows` because the GUI and image
plugins use Windows-only APIs, but CTFAK.Core's *readers* are pure
managed code. The documented Linux path is an **external** patch (kept
in the same external AGPL repo as the plugin, never here) retargeting
`CTFAK.Core` + `CTFAK.Cli` + the InventoryDump plugin to `net6.0` and
building only those three projects. This is exactly the kind of
modification the AGPL permits and this repo's boundary requires to stay
outside.

The constructed invocation (see `ctfak_invocation()`):

```
dotnet <IWG_CTFAK_DIR>/Interface/CTFAK.Cli/bin/Release/net6.0[-windows]/CTFAK.Cli.dll \
    -path /abs/path/to/iwbtgbeta(fs).mfa \
    -tool InventoryDump \
    -out build/iwbtg_mfa
```

`run_ctfak()` requires the registration gate to pass first, runs the
process with a timeout, and expects `inventory_dump.json` in the output
directory; anything else is a hard failure, never a silent skip.

## 4. The `ctfak-inventory-dump/1` contract

The external plugin serializes **metadata only** — names, handles,
coordinates, numeric parameters, chunk ids. Never images, sounds, or any
other expressive asset. Field names mirror CTFAK.Core's public model
(verified by reading the pinned revision's source): `MFAData`
(version/subversion/product/build, window, `MFAValueList` global
values/strings, frame order), `MFAObjectInfo` + loaders (`MFAActive`,
`MFACounter`, `MFAExtensionObject`, …) with qualifiers, groups, parents,
`MFAMovements`/`MFAMovement` (type, extension, player, moving/direction
at start, parameters), `MFAFrame` (size, layers, `MFATransition`s,
instances with ids and object handles), `MFAEvents` (`Evts` chunk →
`List<EventGroup>` with flags, restriction, identifier, nested-group
containers, and `Conditions[]`/`Actions[]` atoms carrying `num`,
`object_type`, `object_handle`, qualifier, and expression lists), plus
every chunk id the reader did not consume (`unknown_chunks`) and every
record the dumper could not fully serialize (`unsupported`).

Top-level document shape:

```json
{
  "dump_format": "ctfak-inventory-dump/1",
  "ctfak_commit": "<pinned commit the dump was produced with>",
  "source_sha256": "<sha256 of the .mfa that was read>",
  "app":        {"name", "mfa_version", "mfa_subversion", "build_version",
                 "product", "window", "frame_order",
                 "global_values": [{"index", "value"}],
                 "global_strings": [{"index", "value"}]},
  "objects":    [{"handle", "name", "type_id", "type_name", "loader_kind",
                  "qualifiers", "group", "parent_handle",
                  "movements": [{"name", "type_id", "type_name", "extension",
                                 "player", "moving_at_start",
                                 "direction_at_start", "params"}],
                  "counter": {"initial", "min", "max"},
                  "unparsed": false}],
  "extensions": [{"handle", "name", "subtype"}],
  "frames":     [{"handle", "name", "size", "layers",
                  "transitions": {"fade_in|fade_out": {"module", "name", "duration"}},
                  "instances": [{"instance_id", "object_handle", "x", "y",
                                 "layer", "flags", "parent_type", "parent_handle"}],
                  "events": {"groups": [{"identifier", "flags", "restricted",
                                         "container", "is_group_marker",
                                         "conditions": [ATOM], "actions": [ATOM]}]}}],
  "unknown_chunks": [{"where", "chunk_id", "size"}],
  "unsupported":    [{"where", "note"}]
}

ATOM = {"num", "object_type", "object_handle", "qualifier",
        "expressions": [ ... ]}
```

## 5. Normalization, provenance, and the fail-closed gate

`tools/importers/iwbtg_mfa/normalize.py` converts a dump into
`iwbtg-normalized-inventory/1`:

- **Counts by record type**: frames, objects, instances, event groups,
  conditions, actions, expressions, movements, counters, extensions,
  transitions, global values/strings, qualifier links, nested groups,
  unknown chunks (cosmetic vs gameplay-relevant).
- **Per-record provenance** back to the MFA identity: every frame
  (`mfa_frame_handle` + name), instance (`mfa_instance_id` +
  `mfa_object_handle`), object/movement (`mfa_object_handle` +
  movement index), and event atom (`mfa_frame_handle`, event group
  index, atom kind, atom ordinal).
- **Fail-closed coverage gate** (`CoverageError`): any unparsed object,
  dangling object-handle or frame-order reference, event atom missing
  its `num`/`object_type` identity, dumper-marked unsupported record, or
  unknown chunk outside the cosmetic set (asset banks `AGMI/ATNF/ASUM/
  APMS`, editor UI state `EvCs/EvEd/EvTs/EvLs`, shaders, comments)
  aborts normalization and lists every blocking record. Nothing is
  silently skipped: every record lands in the inventory or in the error.

CLI: `python -m tools.iwimport mfa-inventory <mfa> [--dump d.json |
--run-ctfak]` — registration gate first, then normalize, then write
`build/iwbtg_mfa/iwbtg_inventory.json` (gitignored) and print the
counts report.

Tests: `tests/test_mfa2pack_spike.py` — 11 tests over a fully
**synthetic** dump (invented names/numbers; no third-party expressive
content): counts + provenance round-trip, every fail-closed branch
(gameplay-relevant unknown chunk, unparsed object, dumper-unsupported,
missing atom identity, dangling handle, dangling frame_order, wrong
format), the registration gate (unregistered + forged record), the
CTFAK resolution gate, and the pinned identities.

## 6. What was extracted / counts by record type

**PENDING — blocked.** No real extraction has run: the canonical `.mfa`
is unreachable from this environment (blocker A) and CTFAK cannot be
built or run here (blocker B). Therefore:

- What CTFAK extracted successfully: **nothing yet** (no run).
- Counts by record type for the real file: **pending** (the report is
  produced automatically by `mfa-inventory` on the first real run).
- Unknown and unsupported records in the real file: **pending**; the
  gate guarantees they surface as a hard failure, itemized, not as a
  silent skip.
- Event-sheet completeness: **structurally supported, unverified on the
  real file.** Reading the pinned CTFAK.Core source shows the `Evts`
  event chunk is fully modeled (event groups, nested groups/containers,
  condition/action atoms with object types and expression lists), and
  MFA-side records the spike needs (movements, counters, transitions,
  qualifiers, globals) all have dedicated readers. That is the basis for
  the structural-feasibility judgment — it is **not** a claim that the
  real file parses cleanly.

## 7. Blockers (precise, with unblock steps)

**A. File transport.** The sandbox's egress allowlist covers only
`github.com`/`api.github.com`/`objects.githubusercontent.com`.
`kayin.moe`, `iwbtg.kayin.moe`, the Google Drive mirror, and archive.org
all return proxy 403s; no GitHub mirror of the `.mfa` exists (searched).
Unblock: allow `kayin.moe` egress for this session, or supply the file
directly; either way `register-iwbtg` must pass (pinned SHA-256) before
anything reads it.

**B. .NET runtime.** No `dotnet`/`mono` is installed and none is
installable (pypi/apt/nuget/dotnet CDNs all blocked). CTFAK has no
release binaries (no tags, archived). Unblock: run the external CTFAK
step on a machine with the .NET 6 SDK (§3) and feed the resulting
`inventory_dump.json` back via `mfa-inventory --dump`.

**C. Independent validation — UNRESOLVED GATE.** The milestone requires
validating CTFAK's output against an independent Clickteam-tooling
source (e.g. a second reader such as anaconda/mmf2 tooling, or MMF2
itself re-exporting verifiable data). No such independent check has been
performed. **CTFAK is not independently validated.** Until a second
tool corroborates at least the frame list, object table, and event-sheet
counts on the real file, every downstream consumer must treat the
inventory as single-source. This gate stays open in the tracker and in
`third_party/classic_source_manifest.toml`.

## 8. Feasibility decision

**Conditionally feasible.** The pinned CTFAK 2.2 reader demonstrably
models every record class the import needs (verified by reading its
source at the pinned commit, not by running it); the repo-side pipeline
(strict registration → external AGPL process → normalized inventory with
provenance → fail-closed coverage gate) is implemented and tested
synthetically. The decision flips to *confirmed* only when, on the real
file: (1) registration passes byte-exactly, (2) `mfa-inventory
--run-ctfak` (or `--dump`) completes with `coverage: PASS`, and (3) the
independent-validation gate (§7C) is resolved. Any gameplay-relevant
unknown or unsupported record on the real file re-opens the decision by
construction — the gate cannot be bypassed silently.

## 9. Next narrowly scoped step

One step, nothing more: on a machine with .NET 6 and the pinned CTFAK
checkout, build the external InventoryDump plugin (published in its own
AGPL repo), run `register-iwbtg` on a byte-verified download of the
canonical `.mfa`, run `mfa-inventory --run-ctfak`, and bring back the
gitignored `iwbtg_inventory.json` counts + any `CoverageError` listing.
That single artifact decides whether event-sheet extraction is complete
enough to specify the IR for the actual import stage — and it is also
where the independent-validation cross-check (§7C) gets its first
numbers to compare against.
