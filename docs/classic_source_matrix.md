# Classic-game source matrix (selection audit, 2026-08-30)

Fresh verification for the classic-track selection milestone. Every
claim about availability, license posture, and repository state below
was re-verified live on 2026-08-30 (the earlier 2026-08-27 audit in
`docs/classic_game_candidates.md` and `third_party/source_manifest.toml`
stands, with the additions noted).  Machine-readable record:
`third_party/classic_source_manifest.toml`.  Selection rationale and
import plans: `docs/classic_exact_import_selection.md`.

Legend for **source tier** (the milestone's hierarchy): T1 public
author-provided source · T2 source shipped with the official game ·
T3 obtainable with creator permission · T4 legally obtained local
project/game data + offline importer · T5 binary extraction only, with
documented absence of source.

## Candidate matrix

| field | IWBTG (original) | Boshy | K2 (original) | K2 WARPED | Kamilia 3 | Crimson Needle 1–3 | IWBT Fangame! | Tribute | LoveTrap |
|---|---|---|---|---|---|---|---|---|---|
| exact game/version | I Wanna Be The Guy, beta build 2008-01-31 (`iwbtgbeta(fs).mfa` — the canonical released game; slomo variant + ALPHA5 2007-12-17 also published) | I Wanna Be The Boshy 1.7.1 | I Wanna Kill The Kamilia 2 (2012 final) | I Wanna Kill the Kamilia 2 WARPED, GitHub HEAD `a6d6dce1` (2022-05-19) | I Wanna Kill The Kamilia 3, v1.30 (2015) / v2.00 (2024) | CN1 / CN2 / CN3 v1.0 (2019) | final 2010-03-09 (+ AGDQ & TAS-friendly 2021 builds) | (unfinished) | 1.x (JP-era) |
| original author | Michael "Kayin" O'Reilly | Solgryn | Influcca (+Kamilia) | SUDALV92 (his own remake/medley of the K2 lineage) | Influcca + Kamilia + ~13 sub-producers | Kale, Zero-G, Nikaple, TheNewGeezer; CN3 + PlasmaNapkin | Tijit (with Matt) | shaman666 | ねころん (Nekoron) |
| source availability | **YES — author-published**: open dir `kayin.moe/iwbtg/source/` + pointer repo `Kayinnasaki/IWBTG` (commit `bb5a6cb5`) + Google Drive mirror; fs/slomo `.mfa` 81 MB each, dated 2008-01-31 (index re-verified 2026-08-30) | NO — only an unofficial, **incomplete** community decompile ("missing a few frames", speedrun.com forum) | NO | **YES — author's own public repo** `SUDALV92/K2W` (re-verified: HEAD `a6d6dce1`, 157 rooms, 1469 objects, 227 scripts hands-on from a fresh clone) | NO — official free itch download only | NO (searched again 2026-08-30: nothing) | NO — official itch downloads alive, no project files | NO (download dead) | NO (original channel expired; only unofficial mirrors/mobile knockoffs) |
| project format | Multimedia Fusion 2 `.mfa` (+ `ending.ccn`) | compiled MMF2 exe; decompile is Clickteam Fusion project | compiled GM8 exe | GameMaker: Studio 1.4 `.project.gmx` XML tree | compiled GM 8.1 exe | CN3 GM:Studio-era presumed (`data.win`); CN1/2 GM8-era | compiled GM8-era exe | unknown | GM8-era presumed |
| engine lineage | Clickteam (MMF2 event sheets) — its own physics, the genre's progenitor | Clickteam MMF2, custom Solgryn physics | GM8 Yuuutu family | Yuuutu family ported to GMS1 (verified in scripts: djump, `vspeed=-jump`, gravity 0.4, water DJ, plus gimmick globals) | GM8.1 Yuuutu family | mixed | GM8-era, ancestor of the first fangame engines | unknown | unknown |
| author-provided source? | **yes** (published by Kayin himself) | no | no | **yes** (the game's own creator) | no | no | no | no | no |
| redistribution allowed | **no** — explicit informal non-grant ("no particular rights… not even the right to view"), published openly all the same; naming request (fangames must not present as official sequels) | no (freeware binary; decompile unauthorized) | no | code: author's blanket permission in README ("completely free to use this code… modding, using part of the code in your projects… publish… without asking"); **embedded third-party medley assets not covered** — never commit the tree | no — itch page reserves copyright to Influcca; third-party contributors retain theirs | no | no ("no copyright intended" disclaimer ≠ license) | n/a | no |
| local source import possible | **yes** — user fetches the author's own `.mfa`; offline Clickteam-format reader (open-source `mmfparser`/Anaconda lineage, GPL) parses it; no binary reverse engineering needed | only via unauthorized incomplete decompile → fails the hierarchy | only via decompile (T5) | **yes** — `git clone` of the author's repo; `.gmx` is plain XML | only via user-provided exe + GM8Decompiler (T5, tolerated-not-authorized) | no path today (CN3 `data.win` track possible later, still T5) | only T5 | no | no |
| source tier | **T1** | T5 (and incomplete) | T5 | **T1** | T5 (T3 worth attempting: ask Influcca) | none | T5 | none | none |
| room count | frames TBD at import audit (single 81 MB `.mfa`; content parallels its own remaster IWBTGR: ~20 room-equivalents over 6 areas) | ~11 worlds | 5 stages + boss rush | **157 rooms** (counted from the tree) | stages 1–4 + boss rush + guest areas + M-Stage (delfruit-documented structure) | CN3: 555 floors | ~40 screens + hub | n/a | ~30 screens + avoidance |
| boss count | 8 (Tyson, MechaBirdo, Kraidgief, Dracula, Bowser/Wart/Wily chain, Mother Brain, Devil Dragon, The Guy — the roster we already ported in its remaster) | ~11 | 5 + final | **38 boss/avoidance rooms** (Boss1–Boss8 chains with phases + avoidances incl. the Miku avoidance) | boss rush + stage bosses + Kamilia finale | few (needle-focused) | several minibosses | n/a | 1 famous avoidance |
| custom mechanic count | moderate: MMF2 physics, ropes/vertical platforms, room-scale set pieces (all in the event sheets) | high (world-specific gimmicks, custom physics) | medium (medley quotes) | high: avoidance patterns, gravity flip (`global.vvvvvv`), dotkid/giant-kid modifiers, infjump/nodjump modes, water variants, medley stage gimmicks — enumerable from 227 scripts | very high (medley of dozens of games) | needle-pure (low count, high precision) | foundational basics | n/a | avoidance patterns |
| overlap with IWannaGym | content overlaps its remaster (already imported) but engine/physics are **entirely new** (Clickteam profile — reserved as `physics.iwbtg_original_2007`, values unextracted by contract) | little engine overlap (new physics) | high (Yuuutu) | **high**: Yuuutu-family player physics ≈ our C core; blocks/spikes/water/platforms/triggers/warps map to existing classes | high (GM8 family) | moderate | high | n/a | moderate |
| expected missing mechanics | Clickteam event-sheet runtime semantics; MMF2 movement/physics profile; rope/ladder & vertical-platform behaviors; `.ccn` ending playback (visual) | whole MMF2 custom-physics engine | GM8 medley gimmicks | GMS1 runtime deltas (audio_*, shaders — visual), avoidance pattern DSL, gravity-flip player state, dotkid/giant hitbox modes | avoidance engine, anti-cheat layers, medley gimmicks | trigger-dense needle (mostly covered) + CN3 scale | early-engine quirks | n/a | avoidance engine |
| expected import complexity | **high** (new `mfa2pack` adapter + physics extraction) but single well-bounded game we know content-wise | very high + unauthorized | medium + unauthorized | **medium** (`gmx2pack` XML adapter; physics mostly reusable; 157 rooms is IWBTGR-scale ×8 content volume, mechanical) | high + unauthorized | high, no source | medium + unauthorized | n/a | n/a |
| cultural importance | **maximal** — the progenitor of the entire genre (2007) | very high (the mainstream gateway fangame) | very high (canonical hard medley) | moderate-high (known SUDALV medley remake; K2/K3 lineage; delfruit-listed) | very high (the canonical hard medley) | very high among needle players (CN3 9.3/10) | high (historically foundational, first-engine ancestor) | low | high (historic Miku avoidance) |

Also swept again for other author-provided full-game sources (GitHub
topic + community searches, 2026-08-30): only engines and tools surface
(iwbte-viri-edition, NANE, renex², YoYoYo, jtool; the open-source
Lockpick *Editor* — the Lockpick game itself remains closed). No
additional T1 game candidates exist today.

## Why the famous ones are not selectable today

- **Boshy**: no author source; the only project files are an
  unofficial, incomplete decompile — fails "exact" and the hierarchy
  both. Re-evaluate only after a Clickteam adapter exists AND with
  Solgryn's permission (T3).
- **Kamilia 3 / Kamilia 2 / Fangame! / CN3 / LoveTrap**: no source;
  the only path is binary extraction (T5). K3's author posture
  (reserved copyright, anti-tool measures) makes an unpermissioned
  decompile irresponsible; it is retained as the optional third
  selection **gated on first attempting creator permission (T3)**.
- **Tribute**: dead distribution, unfinished, low importance — dropped.

Sources consulted (2026-08-30): [Kayinnasaki/IWBTG](https://github.com/Kayinnasaki/IWBTG),
[kayin.moe source dir](https://kayin.moe/iwbtg/source/),
[SUDALV92/K2W](https://github.com/SUDALV92/K2W),
[Influcca's itch page](https://influcca.itch.io/iwktk3),
[Boshy source thread (speedrun.com)](https://www.speedrun.com/iwbtboshy/forums/w59cg),
[tijit.itch.io](https://tijit.itch.io/i-wanna-be-the-fangame),
[Delicious-Fruit K3](https://delicious-fruit.com/ratings/game_details.php?id=14681),
[Delicious-Fruit K2W](https://delicious-fruit.com/ratings/game_details.php?id=21715),
[mmfparser/Anaconda lineage](https://github.com/fnmwolf/Anaconda).
