"""Generate the content-coverage table (docs/coverage_table.md +
build/coverage/coverage.json).

Separates the four content families and, for each, records: source pin,
extraction status, fidelity checks, completion-witness status, scored
eligibility, and PufferLib execution status. Original IWBTG and Remastered
are kept STRICTLY distinct. Counts are read live from the registry, the
witness directory, and on-disk build artifacts; provenance pins are read
from the committed manifests. No fidelity is weakened to inflate counts.
"""
from __future__ import annotations

import json
import os
import tomllib

import iwanna_gym.discovery.registry as R

PACK_DIR = "build/games"
CTFAK_DIR = os.environ.get("IWG_CTFAK_DIR")


def _exists(p):
    return os.path.exists(p)


def _counts():
    reg = R.load_registry()
    nat = [t for t in reg.values() if t.suite == "iwbtg_native"]
    ctl = [t for t in reg.values() if t.suite == "controlled"]
    def wit(ts):
        return sum(1 for t in ts if t.witness_status == "witnessed")
    def act(ts):
        return sum(1 for t in ts if t.active)
    return {
        "native_accepted": len(nat), "native_witnessed": wit(nat),
        "native_active": act(nat),
        "controlled_accepted": len(ctl), "controlled_witnessed": wit(ctl),
        "controlled_active": act(ctl),
    }


def _informative_rooms():
    d = "iwanna_gym/levels/informative"
    return sorted(f[:-4] for f in os.listdir(d)) if os.path.isdir(d) else []


def build():
    c = _counts()
    classic = tomllib.load(open("third_party/classic_source_manifest.toml", "rb"))
    sel = {s["name"]: s for s in classic.get("selected", [])}
    orig = sel.get("iwbtg_original_2007", {})
    gate = classic.get("iwbtg_mfa_extraction_gate", {})
    iwbtgr_pack = os.path.join(PACK_DIR, "iwbtgr_1_5_3.iwpack")
    k2_pack = os.path.join(PACK_DIR, "k2warped_gms14.iwpack")

    families = [
        {
            "family": "iwbtg_original_2007 (ORIGINAL)",
            "role": "future headline; distinct from Remastered",
            "source_pin": f"{orig.get('source_file_url','kayin.moe')} "
                          f"sha256={orig.get('checksum_sha256','?')[:12]}… "
                          f"({orig.get('source_size_bytes','?')} B, "
                          f"{orig.get('format','?')})",
            "extraction_status": "BLOCKED — no byte-verified .mfa in sandbox; "
                                 "importer needs a USER-provided copy + external "
                                 "CTFAK 2.0. Parser/normalizer validated on "
                                 "synthetic dumps only (NOT an extraction).",
            "fidelity": "n/a (nothing extracted)",
            "witness": "n/a (no tasks)",
            "scored_tasks": 0,
            "puffer_exec": "n/a (no content)",
        },
        {
            "family": "iwbtgr_1_5_3 (REMASTERED)",
            "role": "source-native headline suite",
            "source_pin": "itch source-of-record (checksum pending) + tested "
                          "mirror github aut0mat1clol/IWBTGR-Autosplitter-mod "
                          "@244c325; pack sha256 c5dafc88… (expected_pack pin)",
            "extraction_status": ("pack built locally, present on disk"
                                  if _exists(iwbtgr_pack) else
                                  "pack NOT built (run the build command)"),
            "fidelity": "source-exact: 20/20 room audits, 24/24 differential "
                        "checks, classified deviation ledger",
            "witness": f"{c['native_witnessed']}/{c['native_accepted']} "
                       f"witnessed ({c['native_accepted']-c['native_witnessed']}"
                       " pending_witness — kept visible)",
            "scored_tasks": c["native_active"],
            "puffer_exec": "4.0.0 binding compiles vs pinned headers; sim-only "
                           "throughput measured; real `puffer train` UNVERIFIED "
                           "(torch blocked in-sandbox)",
        },
        {
            "family": "controlled (iwannagym_research_v1)",
            "role": "experimental laboratory; never IWBTG content",
            "source_pin": "authored research rooms "
                          "(scripts/make_trap_rooms.py, make_informative_rooms.py)",
            "extraction_status": "n/a (authored, not extracted)",
            "fidelity": "n/a (not source content); deterministic + leak-free "
                        "observation modes (paired anti-leakage tests)",
            "witness": f"{c['controlled_witnessed']}/{c['controlled_accepted']} "
                       f"accepted witnessed; +{len(_informative_rooms())} "
                       "informative-failure control fixtures (not scored)",
            "scored_tasks": c["controlled_active"],
            "puffer_exec": "4.0.0 binding + config exercised; controlled sim "
                           "throughput measured; real train UNVERIFIED (torch)",
        },
        {
            "family": "k2warped_gms14 (OOD)",
            "role": "OOD transfer only; never pooled into headline",
            "source_pin": "SUDALV92/K2W GMS1.4 .gmx @ commit a6d6dce1… "
                          "tree 72c80cc3…",
            "extraction_status": ("STATIC ONLY — pack on disk, but dynamics "
                                  "NOT imported (gameplay records "
                                  "mapping_status=unsupported)"
                                  if _exists(k2_pack) else "pack NOT built"),
            "fidelity": "static structure only (rooms, dims, room order, "
                        "boss locations, event/code inventory)",
            "witness": "0 (no executable tasks)",
            "scored_tasks": 0,
            "puffer_exec": "n/a (no accepted tasks; dynamics gate open)",
        },
    ]
    return {"counts": c, "ctfak_available": bool(CTFAK_DIR and
                                                 os.path.isdir(CTFAK_DIR)),
            "families": families,
            "extraction_gate": {
                "registration_command": gate.get("registration_command", ""),
                "remaining_artifacts": [
                    "a USER-provided byte-verified iwbtgbeta(fs).mfa "
                    "(sha256 c41928c4…, 85.3 MB) staged in the sandbox — the "
                    "importer consumes a user-fetched copy; autonomous download "
                    "of the copyrighted binary is out of scope",
                    "an external CTFAK 2.0 build at IWG_CTFAK_DIR "
                    "(pinned commit f38ba79) — AGPL, run as a separate process",
                    "the iwbtg_original_2007 physics profile extracted per "
                    "docs/fidelity_contract.md before any exactness claim",
                ],
                "network_note": "kayin.moe is reachable at the network level, "
                                "but this sandbox's web-fetch policy forbids "
                                "downloading URLs via curl/wget/python (a "
                                "compliance guardrail, NOT copyright), so the "
                                ".mfa cannot be staged here; run the download on "
                                "the provisioned machine. The external CTFAK 2.0 "
                                "dump producer is confirmed ABSENT here (no "
                                "dotnet/mono; IWG_CTFAK_DIR unset). The registry "
                                "byte-verify + normalize_dump are proven on a "
                                "SYNTHETIC dump only (not an extraction). Exact "
                                "end-to-end commands: docs/iwbtg_extraction_runbook.md.",
            }}


def render_md(data) -> str:
    L = ["# Content coverage table",
         "",
         "Generated by `scripts/coverage_table.py` (live counts from the "
         "registry + on-disk artifacts; pins from the committed manifests). "
         "Original IWBTG and Remastered are DISTINCT families and never "
         "conflated. Fidelity is never weakened to raise task counts.",
         ""]
    for f in data["families"]:
        L += [f"## {f['family']}",
              "",
              f"- **Role**: {f['role']}",
              f"- **Source pin**: {f['source_pin']}",
              f"- **Extraction status**: {f['extraction_status']}",
              f"- **Fidelity checks**: {f['fidelity']}",
              f"- **Completion witness**: {f['witness']}",
              f"- **Scored (active) tasks**: {f['scored_tasks']}",
              f"- **PufferLib execution**: {f['puffer_exec']}",
              ""]
    g = data["extraction_gate"]
    L += ["## Original-IWBTG extraction gate — exact remaining artifacts",
          "",
          f"Registration command: `{g['registration_command']}`",
          "",
          g["network_note"],
          "",
          "Remaining (all required; none present in-sandbox):"]
    for a in g["remaining_artifacts"]:
        L.append(f"- {a}")
    L += ["",
          f"External CTFAK 2.0 available at IWG_CTFAK_DIR: "
          f"**{data['ctfak_available']}**.",
          ""]
    return "\n".join(L)


def main():
    data = build()
    os.makedirs("build/coverage", exist_ok=True)
    with open("build/coverage/coverage.json", "w") as f:
        json.dump(data, f, indent=2)
    with open("docs/coverage_table.md", "w") as f:
        f.write(render_md(data))
    print(render_md(data))
    print("wrote docs/coverage_table.md and build/coverage/coverage.json")


if __name__ == "__main__":
    main()
