# Third-party sources policy

This directory documents every external source iwanna-gym derives exact-game
content or engine semantics from. The machine-readable record is
`source_manifest.toml`; the audit narrative is in
`docs/exact_game_source_audit.md` and `docs/classic_game_candidates.md`.

## What is and is not committed

**Never committed to this repository:** third-party game binaries, game
archives (`.mfa`, `.gmk`, `.gm81`, `.gm82`, `.gmx`, `.exe`, `.zip`,
`data.win`), music, sprites, or any other third-party asset — unless the
applicable license or explicit permission clearly allows redistribution.
As of this audit, **no third-party game source qualifies**: even the most
generous grants (Kayin's "steal a little… do as you will" non-license, the
renex² engine license, SUDALV92's informal blanket permission for K2W) are
either not formal redistribution licenses or cannot cover the third-party
assets embedded inside the files. Community-tolerated decompilation output
(e.g. of Kamilia 3) is categorically excluded.

**Committed instead:** offline importers (when implemented), pack schemas,
this policy, the source manifest with provenance and checksums, and
importer-generated *fixtures* that contain no third-party expression beyond
what fidelity verification requires (counts, coordinates checksums, room
graphs).

## Pipeline architecture

```text
user-provided original source/game files      (never committed; user obtains
        ↓                                      them from the manifest's
offline importer                               source_location)
        ↓                                     (committed; verifies the input
compact IWannaGym game pack                    against manifest checksums)
        ↓                                     (generated locally; content-
native C/PufferLib runtime                     exact per docs/fidelity_contract.md)
```

The importer refuses inputs whose checksum does not match a manifest entry,
so every generated pack is traceable to a precisely identified source
version. Licensing of generated packs follows the source: packs derived
from unlicensed sources are built and used locally by the user, not
redistributed by this project.

## GPL/AGPL tooling note

Several candidate importer components are GPL/AGPL (Gmk-Splitter,
LateralGM, OpenGMK/GM8Decompiler, CTFAK 2.0, mmfparser). This repository is
MIT; those tools are therefore used **as external processes** (documented
dependencies the user installs, invoked by the importer), or replaced by
clean-room parsers written from format knowledge. GPL code is not vendored
into this repository.

## Checksum conventions

- Git-hosted sources are pinned by **commit SHA** (itself a content hash);
  where a working tree was inspected locally, an additional
  `tree_sha256` is recorded, computed as:
  `find . -type f -not -path './.git/*' -print0 | sort -z | xargs -0 sha256sum | sha256sum`
  (i.e. sha256 over the sorted list of per-file sha256 lines).
- Plain-file sources get `sha256` of the exact archive/file.
- `checksum_status = "pending"` means the file is verified to exist at the
  recorded location (with size/date noted where the host lists them) but was
  not downloadable from the audit sandbox; the checksum MUST be computed and
  filled in the first time an importer consumes the file, before any pack it
  produces is called exact.

## Attribution and conduct

Kayin's stated request — that fan works not present themselves as official
IWBTG sequels — is honored: imported packs carry the source game's own name
and version identifier and are labeled as research reproductions. Authors'
copyrights in games, engines, music, and art remain with their holders;
inclusion in the manifest is a citation, not a claim of rights. If any
author asks for their source's removal from the manifest or objects to an
importer, that request will be honored.
