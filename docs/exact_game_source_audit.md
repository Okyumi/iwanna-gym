# Exact-game source audit

Audit date: 2026-08-27. Every claim below was verified against the cited
primary source on that date unless explicitly marked otherwise. Machine-
readable records for each source (pinned commits, checksums, availability)
live in `third_party/source_manifest.toml`; redistribution policy lives in
`third_party/SOURCES.md`; what "exact" means lives in
`docs/fidelity_contract.md`.

Scope: prepare iwanna-gym to import complete, precisely identified games by
existing I-Wanna creators, starting with *I Wanna Be The Guy*. This audit
locates the sources; it does not implement importers.

---

## 1. Original *I Wanna Be The Guy* (`iwbtg_original_2007`)

**Engine.** Multimedia Fusion 2 (MMF2) — Kayin's own FAQ: "IWBTG is made,
unfortunately, in Multimedia Fusion 2. Not Flash."
(https://iwbtg.kayin.moe/faq.html). Any assumption that the original is a
GameMaker game is wrong.

**Source release.** Kayin released the full MMF2 source. The GitHub repo
[Kayinnasaki/IWBTG](https://github.com/Kayinnasaki/IWBTG) (pinned commit
`bb5a6cb`, README sha256 `ee87757b…801fdc7b`) is a pointer README only —
GitHub file-size limits — with the actual archives on two mirrors:

- https://kayin.moe/iwbtg/source/ (open directory; verified listing):
  - `iwbtgALPHA5.mfa` — 81 MB, 2007-12-17
  - `iwbtgbeta(fs).mfa` — 81 MB, 2008-01-31
  - `iwbtgbeta(slomo).mfa` — 81 MB, 2008-01-31
  - `iwstkalpha12.mfa` / `iwstkalpha133.mfa` (I Wanna Save the Kids, 4 MB)
  - `ending.ccn` — 6.3 MB compiled Clickteam file (ending cutscene)
- Google Drive mirror linked from the README (existence verified, download
  not exercised).

The two 2008-01-31 "beta" builds — `(fs)` and `(slomo)` — are the final
source snapshots; the shipped game never carried a clean numeric version
(a "1.0.0" could not be verified from any primary source; the game's last
official update was February 2008). **Version identification for
`iwbtg_original_2007` therefore pins the specific `.mfa` file (fs or slomo)
by checksum, not a version number.** Checksums of the `.mfa` files could not
be computed in this audit environment (kayin.moe is not reachable from the
sandbox; sizes/dates above are from the fetched directory index) — computing
and recording them is the first step of importer work.

**Terms.** Deliberately informal: "IWBTG is under no particular license, and
I grant you no particular rights. … *you gotta steal a little*. … **Do as you
will.**" (repo README, quoted in full in `third_party/SOURCES.md`), plus
Kayin's FAQ: "My source code is basically released under a 'license' that
says 'steal from me, please'", non-commercial-without-asking for companies,
explicit "no crypto/NFT". His only request is that fangames not present
themselves as official sequels. This is generous but is **not** a
redistribution license — see `third_party/SOURCES.md` for why the `.mfa`
files stay out of this repository.

**What it gives us.** The `.mfa` embeds the entire authored game: all frames
(rooms), object placements, event logic (triggers, bosses), and assets. It is
the only authoritative source for original-2007 physics and content. Reading
it requires Clickteam tooling or the open-source MMF parsers (mmfparser /
CTFAK 2.0 — §4). Kayin himself warns the files are "best used *as
reference*" and partially broken in current MMF2 (vertical platforms).

**Room graph availability: yes in principle** — contained in the `.mfa`,
extraction unproven until an importer exists. No third party publishes IWBTG
room data in machine-readable form.

## 2. *I Wanna Be The Guy: Remastered* 1.5.3 (`iwbtgr_1_5_3`)

**Identity.** By Cherry Treehouse (Natsu), Renko, renex, Floogle; released
2020-12-22; endorsed by Kayin, whose downloads page designates it "the
recommended version of the game." Version 1.5.3 is real and current
(itch.io page, verified 2026-08-27).

**Engine.** GameMaker 8.2 (community-patched GM 8.1; devs state "we use
8.1.141" + GM8.2 patch) on the **Yuuutu engine**, prepatched with gm8x_fix
(Delicious-Fruit entry id=22751; dev comments on itch). Kayin: the team
rebuilt IWBTG "from the ground up in game maker", moving it "to Yuuutu
fangame physics", with "as much as possible … copied from original MMF2
source code".

**Source availability.** The itch page
(https://cherry-treehouse.itch.io/iwbtgr) publicly serves both
`IWBTGR 1.5.3.zip` (49 MB, game) and **`IWBTGR Source 1.5.3.zip` (3.7 MB,
the GameMaker project)** — an author-released, buildable source package
(a commenter built it; renex answered with the GM-version requirement).
itch.io generates download URLs dynamically, so the page URL is the access
point; the zip could not be downloaded from this audit sandbox, so its
checksum and internal layout (monolithic `.gm81`/`.gm82` file vs. gm82save
per-resource text tree) are recorded as *pending* in the manifest. Either
layout is machine-readable with existing open tooling (§4).

**Terms.** No explicit license text on the itch page for the source zip.
Kayin's blanket stance covers the IWBTG IP; the Remastered team's own terms
are unstated. Treated as *source-available, redistribution unclear* → the
zip is never committed; users supply it to the importer.

**What it gives us.** The complete canonical game as GM8 data: every room
with instance lists (x, y, object, creation code), object event/GML code
(bosses, triggers, saves, difficulty gating), the room graph, and the
Yuuutu player object. This is the complete room graph and object data of
the modern canonical IWBTG, in the same engine family the iwanna-gym C core
already reproduces.

## 3. Engines (logic references)

- **renex² engine** — upstream repo
  [omicronrex/renex2-engine](https://github.com/omicronrex/renex2-engine)
  (the previously referenced `RainbowSea5/renex-engine` is a fork of it;
  "renex" v1 and "renex²" are one continuously developed project, v1.8.0
  Dec 2024). GM8.2, stored in the gm82save **text** format (per-resource
  .gml/.txt + plain-text rooms) — machine-readable with no binary parsing.
  Custom permissive license (free use incl. commercial games w/ FMOD caveat;
  no engine resale; no crypto). Built by renex & Square using Guy Remastered
  as base; credits Yuuutu. Pinned `5c0047d`, tree sha256 `ff934ca7…`.
  **The current iwanna-gym physics was ported from this engine's player
  code, and this audit re-verified the constants in its GML source** (jump
  8.5 / jump2 7 / maxSpeed 3 / grav 0.4 / maxVspeed 9 / release ×0.45 /
  50 Hz). This existing implementation is correct and is retained as-is.
- **Zephyr GM8.2 engine** —
  [orzephyrous/IWBT-GM8.2-Engine-Zephyr-Edition](https://github.com/orzephyrous/IWBT-GM8.2-Engine-Zephyr-Edition),
  independent corroboration of the same constants (pinned `7a3ec3e`).
- **Yuuutu engine** ("I wanna be the engine yuuutu edition", by ゆううつ) —
  the classic Japanese GM8 engine IWBTGR is built on; distributed informally
  via the アイワナまとめ@wiki page (w.atwiki.jp/iwannabethewiki/pages/484.html)
  → MediaFire; no license text anywhere; Delicious-Fruit's own link currently
  dead. Historically central, but as a *source of truth* it is superseded
  for our purposes by IWBTGR's own source (which embeds the Yuuutu player)
  and by renex²/Zephyr (which are maintained and pinned). Recorded in the
  manifest as reference-only with availability *fragile*.

## 4. Project-reading / decompiling tools

GameMaker 8 family:

- **OpenGMK** ([OpenGMK/OpenGMK](https://github.com/OpenGMK/OpenGMK), Rust,
  GPL-2.0, active 2026): GM8 runner/emulator + decompiler + `gm8exe` parsing
  crate. **Operates on compiled `.exe` only — it does not read `.gmk`/`.gm81`
  project files** (open feature request, issue #141). Includes a TAS
  framework (potentially useful later for trajectory verification).
- **GM8Decompiler** ([OpenGMK/GM8Decompiler](https://github.com/OpenGMK/GM8Decompiler),
  GPL-2.0, v2.2.0): any GM8.0/8.1 `.exe` → reconstructed `.gmk`/`.gm81`
  project (sprites, objects+GML, rooms with instances).
- **LateralGM** ([IsmAvatar/LateralGM](https://github.com/IsmAvatar/LateralGM),
  Java, GPL-3.0): reads `.gmk`/`.gm81` project files directly
  (`GmFileReader.java`, format versions 530/600/701/800/810; rooms with
  per-instance object ref, x/y, id, creation code). The best open reference
  implementation of the project-file format.
- **Gmk-Splitter** ([Medo42/Gmk-Splitter](https://github.com/Medo42/Gmk-Splitter),
  Java, GPL-3.0): `.gmk`/`.gm81` ⇄ per-resource XML/GML text tree, built on
  LateralGM's reader — practically the exact shape of importer front-end we
  need, reusable by shelling out (GPL stays at arm's length from our MIT
  code; see SOURCES.md).
- **gm82save** ([GM82Project/gm82save](https://github.com/GM82Project/gm82save),
  Rust): defines the `.gm82` per-resource text format (used by renex²);
  importing that format is plain text/INI+GML parsing.
- GM:Studio-era games (`data.win`) would use **UndertaleModTool** (GPL-3.0);
  not needed for GM8-era targets.

Clickteam/MMF family (for `iwbtg_original_2007` and Boshy):

- **mmfparser / Anaconda** (Mathias Kaerlev; surviving mirror
  [Matt-Esch/anaconda](https://github.com/Matt-Esch/anaconda), GPL +
  commercial dual): Python parsers for MMF2 data (chunk reader, frames,
  object instances, events, images; MMF1.5-era chunks supported). The 2012
  mirror lacks the `.mfa` editor-format module; later decompiler forks carry
  fuller `.mfa` handling.
- **CTFAK 2.0** ([CTFAK/CTFAK2.0](https://github.com/CTFAK/CTFAK2.0), C#,
  AGPL-3.0, archived/unmaintained): reads built `.exe`/`.ccn`/`.dat` **and
  `.mfa`**, with MMF-1.5-mode switches and MFA-reconstruction output. Best
  current open route into the IWBTG `.mfa`; its archived status is a known
  risk (successor "NebulaFD" is work-in-progress).

## 5. Recommended first exact-game target: `iwbtgr_1_5_3`

Recommendation: **implement the first exact full-game import from the
IWBTGR Source 1.5.3 package**, with the original `.mfa` retained as the
logic/content reference it was for the Remastered team itself.

Justification:

1. **Author-released, machine-readable source of the complete game.** The
   3.7 MB GameMaker project is the entire canonical game as structured data;
   GM8-family project formats have multiple working open readers (§4),
   versus the `.mfa` route which depends on an archived AGPL tool or
   substantial parser work.
2. **Physics continuity.** IWBTGR runs Yuuutu-engine physics — the same
   family the iwanna-gym C core already implements with verified constants.
   An IWBTGR import exercises content fidelity without simultaneously
   requiring a second physics engine. An original-2007 import would require
   extracting and reimplementing the (currently numerically unknown) MMF2
   movement first — see `docs/fidelity_contract.md`.
3. **Canonical status.** Kayin endorses Remastered as the recommended
   version; it is the version the community actually plays today, and it is
   precisely identifiable (`1.5.3`).
4. **Honest labeling is preserved.** The import will be documented as
   Remastered content + Yuuutu physics (`iwbtgr_1_5_3`), never as "the
   original 2007 game". `iwbtg_original_2007` remains a distinct future
   target whose physics work starts from the `.mfa`.

Risks / open items for the importer phase (tracked in the manifest):
download and checksum `IWBTGR Source 1.5.3.zip`; determine its internal
format (monolithic vs gm82save tree); diff the IWBTGR player object against
the C core before claiming physics-verified; enumerate GML features used by
boss/trigger code to size the event-import work; the source zip's formal
license is unstated, so the pack pipeline must stay user-provided (see
`third_party/SOURCES.md`).

## 6. What already existed in this repo (retained)

The C core's renex-derived physics and its analytic tests predate this audit
and were confirmed against the pinned renex² source — they are retained
unchanged. The entity/event/gate systems and the 20 trap rooms are original
research content (`iwannagym_research_v1`), unaffected by this audit except
for being explicitly labeled as a separate benchmark family. Nothing was
reimplemented as part of this audit; no importer is implemented yet.

## 7. Classic-game audit summary

See `docs/classic_game_candidates.md` for the seven-family audit (Boshy,
Kamilia 2/3, Crimson Needle 1–3, I Wanna Be The Fangame!, Tribute, LoveTrap,
plus open-source engines/tools) and the ranked import candidates.
