# Classic exact-import selection (2026-08-30)

Selection of the next two classic games for complete, exact import,
per the source hierarchy and the candidate matrix
(`docs/classic_source_matrix.md`; machine-readable pins in
`third_party/classic_source_manifest.toml`).  **No implementation
happens in this milestone** — this document is the reviewed decision
record.  Both selections import the actual rooms, mechanics,
progression, saves, and bosses authored by the original creators from
their own published project files; no homage or manually designed
replacement is involved anywhere below.

## The selections

```
CLASSIC_GAME_1 = iwbtg_original_2007
                 I Wanna Be The Guy (Kayin, beta build 2008-01-31,
                 iwbtgbeta(fs).mfa from the author's own source release)

CLASSIC_GAME_2 = k2warped_gms14
                 I Wanna Kill the Kamilia 2 WARPED (SUDALV92,
                 GitHub SUDALV92/K2W @ a6d6dce1, 2022-05-19)
```

```
CLASSIC_GAME_3 (optional, gated) = iwktk3
                 I Wanna Kill The Kamilia 3 — ONLY IF creator
                 permission is obtained first (tier 3); otherwise the
                 documented user-provided-exe decompile path stays a
                 proposal, not a selection.
```

### Why CLASSIC_GAME_1 is IWBTG itself

The milestone's rubric asks for the strongest combination of
recognizability, exact source availability, feasibility, mechanic
diversity, and scientific value — and warns against picking fame
without a responsible source. IWBTG original is the one candidate
where fame and source coincide: it is the progenitor of the entire
genre, and Kayin published the actual MMF2 project files himself
(tier 1 — the only tier-1 source among the famous candidates; Boshy
and Kamilia 3 both fail the hierarchy). Scientifically it is the
strongest possible pick: a second, genuinely different engine family
(Clickteam event sheets) and a new physics profile — and because we
already ship its GameMaker remaster (`iwbtgr_1_5_3_v1`), importing
the original creates the benchmark's first *cross-engine pair of the
same franchise content*: near-identical level semantics under two
authentic physics models (transfer and generalization studies the
Yuuutu-only track cannot support). It also discharges the standing
fidelity-contract obligation that `physics.iwbtg_original_2007`
remain "values unextracted" until derived from the released project
files — this import is exactly that derivation.

### Why CLASSIC_GAME_2 is K2 WARPED

K2W is the only complete classic-community fangame whose author
publishes the full project publicly AND grants blanket code reuse in
writing. It is a real released game by its own creator (SUDALV92's
hard-mode medley remake in the K2/K3 lineage, listed on
Delicious-Fruit) — importing it imports *his* authored rooms and
bosses, not a homage of ours; the pack will be labeled as K2 WARPED,
never as Kamilia 2. Verified hands-on from a fresh clone: 157 rooms,
38 boss/avoidance rooms (eight boss chains with phases, including a
Miku avoidance), 1,469 objects, 227 scripts, 854 sprites, GameMaker:
Studio 1.4 `.project.gmx`. Its player physics are Yuuutu-family
(verified in the scripts: djump, `vspeed = -jump`, gravity 0.4, water
double-jump), so the existing C core carries most of the movement
layer, while the game adds what our benchmark lacks most: avoidance
bosses (choreographed bullet patterns), gravity-flip mode, dotkid /
giant-kid hitbox modifiers, and a third source format (GMS 1.4 XML)
for the importer family.

Together the two selections cover: a new engine family + new physics
profile (game 1), a new project format on mostly-reused physics
(game 2), the genre's most recognizable title (game 1), a
boss/avoidance-rich modern medley (game 2) — with both sources
author-provided.

## Import plan — CLASSIC_GAME_1: iwbtg_original_2007

| item | plan |
|---|---|
| source version | `iwbtgbeta(fs).mfa`, dated 2008-01-31, 81 MB — the canonical released game (IWBTG shipped as "beta"; the fs build is the standard one). Secondary reference: `iwbtgbeta(slomo).mfa` (timing variant) and `iwbtgALPHA5.mfa` (2007-12-17) for provenance cross-checks. `ending.ccn` is compiled (visual ending; expected unsupported). |
| source checksum | verified from the author-hosted file on 2026-09-01: 85,300,282 bytes; SHA-256 `c41928c4e6599b3535c7a1d0d4b0df4da6068184e037a899af4282b460678f76`. `python -m tools.iwimport register-iwbtg '/path/to/iwbtgbeta(fs).mfa'` refuses any filename, size, or digest mismatch and writes only a gitignored local record. Mirrors are transport alternatives only when byte-identical. Pointer repo: `Kayinnasaki/IWBTG` @ `bb5a6cb5`. |
| importer adapter required | new `mfa2pack`: CTFAK 2.0 reads the `.mfa` directly as an external AGPL process → normalized source-derived IR → the existing gamepack pipeline. The first gate inventories frames, objects/instances, qualifiers/groups, movements, complete event sheets, globals/counters/transitions/extensions, and unknown records. Gameplay-relevant unknowns fail closed. Validate the extraction independently with compatible Clickteam/MMF tooling before porting gameplay. |
| physics profile | **new** `iwbtg_original_2007`, extracted from the `.mfa` player object's movement + events (per the fidelity contract, no "original physics" claim before this extraction). The C core gains a second player-step implementation behind the profile switch. |
| reusable existing mechanics | the pack format, exact-layer entity/trigger/warp/save machinery, boss-slot framework, coverage gates, audit/differential/freeze tooling — and complete content knowledge of the same roster from the IWBTGR import (8 bosses, save/difficulty semantics, progression) as a semantic cross-reference (never a substitute for the source). |
| new object classes | MMF2 movement types (bouncing-ball/path/platform movements as used), rope/ladder handling, vertical platforms (author-flagged as broken in modern MMF2 — must come from the event semantics, documented), MMF-style counters/globals, room-transition fades (visual-simplified). Estimate: on the order of the IWBTGR exact-layer class count, mostly parallel ports. |
| boss work | the original versions of the 8 known bosses re-transliterated from MMF2 event sheets (patterns/timings differ from the remaster; no reuse without verification against the sheets). |
| estimated unsupported areas | `.ccn` ending playback (visual); any mouse/menu-only interactions; MMF2 audio; possible per-build timing quirks between fs/slomo builds (documented, fs is canonical). |
| redistribution strategy | never commit or redistribute the `.mfa` or any embedded asset (author grants no rights; files are his published reference). Committed: importer, manifest pins, fixtures limited to counts/checksums/room graphs. Honor Kayin's naming request. Before implementation, send a courtesy note to Kayin describing the project (tier-3 politeness on top of tier-1 availability). |
| verification strategy | same discipline as `iwbtgr_1_5_3_v1`: coverage-gated build, room audit vs the `.mfa` tree, differential validation against source-derived expected values (movement recurrences extracted from the event sheets), pinned reference traces, full-game completion driver, content-checksum freeze as `iwbtg_2007_v1` — plus the new cross-engine check: IWBTG-original vs IWBTGR progression graphs compared structurally. |

## Import plan — CLASSIC_GAME_2: k2warped_gms14

| item | plan |
|---|---|
| source version | GitHub `SUDALV92/K2W`, commit `a6d6dce1fe21f759f9e2218c9f9445c051667ad6` (2022-05-19), tree `72c80cc39be972889d2cfcff8a3a946357ac19eb` — pinned exactly; the repo is the author's living project (any later commit would be a new freeze). |
| source checksum | the git commit + tree hashes above ARE the reproducible identity (verified from a fresh clone today); the importer additionally records sha256 of the `.project.gmx` and per-room `.room.gmx` files at build time. |
| importer adapter required | new `gmx2pack`: GMS 1.4 XML reader (rooms/instances/objects/scripts are plain XML/GML text — same architecture as the gm82save text importer, different schema). GML dialect deltas (GMS1 functions like `audio_*`) handled by the same lowering table approach. |
| physics profile | `iwannagym_renex` largely reusable — the scripts implement Yuuutu-family movement; a GMS1 delta audit (any changed constants/order) runs first, and if the audit finds real differences the pack gets a documented `k2w_gms14` profile variant instead of a false "same physics" claim. |
| reusable existing mechanics | the entire GM-track runtime: blocks/spikes/killers, saves (shoot semantics to verify against its scripts), warps, triggers, water, platforms, cameras, boss slots, path playback, coverage/audit/freeze tooling. |
| new object classes | avoidance-boss pattern machinery (choreographed spawner scripts — 227 scripts enumerable up front), gravity-flip player state (`global.vvvvvv`), dotkid/giant-kid hitbox modifiers, `noDJump`/`infJump` modes, medley stage gimmicks, GMS1 timelines (8 dirs in `timelines/`). |
| boss work | 38 boss/avoidance rooms across eight chains (multi-phase bosses + standalone avoidances) — the project's largest work item; each ports as a native state machine on the existing boss framework, driven by its own GML. |
| estimated unsupported areas | shaders and visual effects (simplified-visual), audio, online/score features if any, achievements screen (meta room); music-sync in avoidances is frame-timed in GML so it imports as timing, not audio. |
| redistribution strategy | the author's blanket code permission covers the import; embedded third-party medley assets are still never committed — the user clones the author's repo (or the importer fetches at build time), and packs are built locally like IWBTGR. Label the pack K2 WARPED by SUDALV92 everywhere; it must never masquerade as Kamilia 2. |
| verification strategy | the frozen-pack discipline: coverage gates over all 157 rooms, room audit against the XML tree, differential validation vs script-derived constants, scripted full-game driver to completion, reference traces, freeze as `k2warped_v1` pinned to commit `a6d6dce1`. |

## CLASSIC_GAME_3 (optional): iwktk3 — permission-gated

Kamilia 3 is the community's canonical hard medley and belongs in the
benchmark eventually, but its only current path is decompilation of a
copyright-reserved binary (tier 5). Proposal: contact Influcca (itch)
requesting project files or import permission (tier 3). If granted:
same GM8.1 pipeline as IWBTGR. If refused or unanswered, K3 is not
imported; the documented user-provided-exe path in the manifest
remains a proposal only. No timeline commitment.

## Order of work (when implementation is authorized)

1. `k2warped_gms14` first — the cheaper adapter (XML) on mostly-reused
   physics, delivering a big, boss-rich second game quickly and
   hardening the multi-game pack tooling.
2. `iwbtg_original_2007` second — the Clickteam adapter and physics
   extraction as its own carefully audited track.

(Reversing the order is defensible if the physics-extraction research
for the contract is prioritized; the selection itself does not change.)
