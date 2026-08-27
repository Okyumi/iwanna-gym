# Classic fangame import candidates

Audit date: 2026-08-27; verification notes as in
`docs/exact_game_source_audit.md`. Games are ranked not by popularity but
by: (1) source/project availability, (2) legal & reproducibility status,
(3) compatibility with existing engine semantics (Yuuutu-family GM8 physics
already implemented in the C core), (4) importance to I-Wanna players,
(5) diversity of mechanics, (6) feasibility of exact import.

Attribution corrections made during this audit (vs. common assumptions):
*I Wanna Be The Fangame!* is by Tijit (with Matt), 2010 — not Sephalos.
*I Wanna Be The Tribute* is credited to shaman666 on Delicious-Fruit.
*I Wanna Be The LoveTrap* is by ねころん (Nekoron). *Not Another Needle
Game* is by Thenewgeezer. Kamilia 2/3 are by Influcca (with Kamilia and,
for K3, ~13 sub-producers).

## Candidate table

| game | author / year | engine | game download | source availability | import feasibility |
|---|---|---|---|---|---|
| IWBTG: Remastered 1.5.3 | Cherry Treehouse et al., 2020 | GM8.2 (Yuuutu) | itch.io (free, official) | **author-released source zip on itch** | **high — recommended first target** (see source audit) |
| I Wanna Kill The Kamilia 2 WARPED (K2W) | SUDALV92 (remake of Influcca's K2) | GM Studio 1.4 (`.project.gmx`) | GitHub | **full project on GitHub; author grants blanket reuse ("completely free to use this code…"), no formal license file** | **high for content extraction** — .gmx is XML text; caveats: GMS1 engine differences, it is a hard-mode *remake* of K2, and third-party medley assets are not covered by the author's permission |
| I Wanna Kill The Kamilia 3 (v1.30 / v2.00) | Influcca + team, 2013–2015 (v2.00 2024) | GM 8.1 | itch.io (free, official) | no source; **mechanically decompilable** (GM8Decompiler); community decompile-based mods circulate openly (K3 EZ, practice mods) | **medium** — technically clean path (user-provided exe → GM8Decompiler → gmk importer), engine family matches the C core; legally decompile-tolerated but unauthorized: user-provided-files only, nothing committed |
| I Wanna Be The Boshy 1.7.1 | Solgryn, 2010–11 | MMF2 | grynsoft.com (freeware; archive.org mirror) | no official source; **unofficial, incomplete community MMF2 decompile** posted on the game's speedrun.com forum | **low-medium** — needs the whole Clickteam toolchain (shared with `iwbtg_original_2007`, so it becomes plausible *after* that importer exists); decompile is incomplete; non-standard physics (not Yuuutu) |
| I Wanna Be The Fangame! (final 2010-03-09) | Tijit (+Matt), 2010 | GameMaker (GM8-era; exact version unconfirmed) | tijit.itch.io (free, official, incl. TAS-friendly build) | no project-file release found | **medium** — historically foundational (first fangame engine ancestor); GM8 decompile path, user-provided |
| Crimson Needle 1 / 2 / 3 | Kale (+Zero-G, Nikaple, TheNewGeezer; CN3 + PlasmaNapkin), CN3 2019 | unconfirmed (CN3 treated as GM-Studio-era by community) | CN3 downloadable; CN1 link dead (as seen anonymously) | none found for any of the three | **low** — no source, engine unconfirmed; CN3 is the genre's needle masterpiece (9.3/10, 120 reviews) so worth revisiting once a data.win path exists, but not an early target |
| I Wanna Be The Tribute | shaman666 | unconfirmed | dead link | none | **drop** — dead download, minor importance (4.1/10, 37 ratings), unfinished |
| I Wanna Be The LoveTrap | ねころん (Nekoron) | unconfirmed (GM8-era presumed) | original link expired | none | **low** — historically notable (Miku avoidance, diff 91.8); only viable as user-provided-exe decompile if a copy is supplied |

Also audited, with released source but not "classic games": the renex²,
Zephyr, YoYoYo (GMS1), and NANE engines; jtool (+ports); K2W above;
I Wanna Lockpick *Editor* (Godot, open source; the Lockpick game itself is
closed); small open-source web remakes (iwbtc, IWBTG.ts). I Wanna Maker is
free but closed with a proprietary online level service; Not Another Needle
Game has no source release (NANE, its public engine, reimplements many of
its gimmicks and is open).

## Ranked recommendations

1. **`iwbtgr_1_5_3`** — first exact full-game target (argued in
   `docs/exact_game_source_audit.md`).
2. **K2W (`k2warped_gms14`)** — first *classic-derived* candidate: the only
   full fangame project on GitHub with an author's blanket permission;
   exercises a second source format (GMS 1.4 `.gmx` XML) at low legal risk.
   Its imported pack must be labeled as the WARPED remake, not as K2.
3. **Kamilia 3 (`iwktk3_1_30` / `iwktk3_2_00`)** — second classic candidate:
   GM8.1 (same family as the existing core), enormous player importance
   (8.1/10, 182 ratings, the canonical hard medley), clean *technical* path
   via user-provided exe + GM8Decompiler + the same gmk importer IWBTGR
   needs. Unauthorized-but-tolerated status means: importer and manifests
   committed, no game files ever committed, and the pack is opt-in built by
   the user from their own copy.
4. **I Wanna Be The Fangame!** — strong third option on historical
   importance and an alive official download; same GM8 pipeline; engine
   version needs confirmation first.
5. **Boshy** — deferred until the Clickteam importer for
   `iwbtg_original_2007` exists; then re-evaluate against the incomplete
   community decompile (its custom MMF2 physics also make it a *new physics
   profile*, which is a feature for benchmark diversity but a cost for
   exactness verification).
6. **Crimson Needle 3** — flagged for a future GM:Studio (`data.win`/
   UndertaleModTool) track; no source today.
7. Tribute and LoveTrap — not viable now (dead links, no source); LoveTrap
   retained on a watchlist for its historical value.

Acceptance status vs. the audit goals: at least five families investigated
(eight, plus engines/tools); at least two plausible classic-game import
candidates identified (K2W, Kamilia 3, with I Wanna Be The Fangame! as a
third).

## Legal / community context (summary)

Fangames are freeware by strong community norm; Delicious-Fruit links to
author-controlled downloads rather than hosting files. Third-party
copyrighted assets (ripped sprites, commercial music) are pervasive — K3's
own itch page notes third-party contributors retain their copyrights —
so **no classic fangame is cleanly redistributable as a whole work**, which
is why the pipeline in `third_party/SOURCES.md` separates committed
importers/manifests from user-provided game files. GM8 decompilation is
openly practiced and community-tolerated (public decompile mods of K3,
Boshy decompiles on official speedrun forums, purpose-built community
tools), but tolerance is not permission; some authors deliberately protect
their games. No DMCA takedowns in the fangame scene were found in this
audit (absence of evidence only). Kayin's request — fangames should not
present as official IWBTG sequels — is honored throughout by the naming and
labeling rules in `docs/fidelity_contract.md`.
