# Original-IWBTG (2007) extraction runbook — exact commands

Concrete, reproducible steps to register and extract the original IWBTG
`.mfa` on a capable machine. Nothing here runs the real extraction in the
authoring sandbox — see "In-sandbox status" for exactly why and what is
blocked. Source bytes and extracted assets are NEVER committed.

## The exact repository instruction (does the repo require a user file?)

Yes — by design. `tools/iwimport/source_registry.py` is titled *"Strict
registration for non-redistributable, user-supplied sources."* Its
`register(source, spec)` takes a LOCAL FILE PATH to an already-present
file, byte-verifies it against the pinned spec, and writes only a local
metadata record — it has **no download step**. The pinned spec
(`IWBTG_ORIGINAL`) is:

    filename  iwbtgbeta(fs).mfa
    size      85300282 bytes
    sha256    c41928c4e6599b3535c7a1d0d4b0df4da6068184e037a899af4282b460678f76
    url       https://kayin.moe/iwbtg/source/iwbtgbeta(fs).mfa

So "user-provided" is baked into the tool: the repo never fetches or
redistributes the copyrighted bytes; it consumes a file the operator has
already placed locally and verifies it is exactly the pinned canonical
source. Copyright is not the gate here (the file is the author's openly
published reference source); the gate is that the tool needs the bytes
present and byte-identical.

## Step 0 — fetch the author-hosted source into a gitignored cache

    mkdir -p build/iwbtg_mfa            # already gitignored (never committed)
    curl -L -o 'build/iwbtg_mfa/iwbtgbeta(fs).mfa' \
        'https://kayin.moe/iwbtg/source/iwbtgbeta(fs).mfa'
    # integrity is REQUIRED — reject any mismatch:
    python - <<'PY'
    import hashlib, pathlib, sys
    p = pathlib.Path("build/iwbtg_mfa/iwbtgbeta(fs).mfa")
    b = p.read_bytes()
    assert len(b) == 85_300_282, f"size {len(b)} != 85300282"
    h = hashlib.sha256(b).hexdigest()
    assert h == "c41928c4e6599b3535c7a1d0d4b0df4da6068184e037a899af4282b460678f76", h
    print("OK", len(b), h)
    PY

## Step 1 — register (byte-verify) the source

    python -m tools.iwimport register-iwbtg 'build/iwbtg_mfa/iwbtgbeta(fs).mfa'
    # writes build/source_registry/iwbtg_original_2007.json (metadata only)

## Step 2 — build the external CTFAK 2.0 dump producer (AGPL, external)

CTFAK 2.0 is AGPL and runs as a SEPARATE process from a user-managed
checkout — never vendored/linked into this MIT repo.

    git clone https://github.com/CTFAK/CTFAK2.0 $HOME/CTFAK2.0
    git -C $HOME/CTFAK2.0 checkout f38ba7951f5fa9d714dc5d97772882ea6aa61717
    # build with .NET 6 (net6.0-windows targets; on Linux apply the retarget
    # patch in docs/iwbtg_mfa_feasibility.md), then:
    export IWG_CTFAK_DIR=$HOME/CTFAK2.0

## Step 3 — run the ACTUAL direct-MFA extraction

    python -m tools.iwimport extract-iwbtg \
        --registry build/source_registry/iwbtg_original_2007.json \
        --ctfak-dir $IWG_CTFAK_DIR \
        --out build/iwbtg_mfa/inventory.json
    # this invokes CTFAK's InventoryDump (metadata only) then normalize_dump,
    # which FAILS CLOSED on any unparsed/unknown/unsupported gameplay record.
    # Report: total records by type, and the unsupported-record ledger.

## Step 4 — outstanding gates (keep separate; do NOT fold into "extracted")

- **Independent Clickteam validation.** Cross-check the CTFAK inventory
  against a second, independent Clickteam reader before trusting counts;
  until then the inventory is single-source.
- **Source-derived physics.** The `iwbtg_original_2007` physics profile
  must be extracted per `docs/fidelity_contract.md` before ANY exactness
  claim. The inventory (structure) does not by itself give physics.

## In-sandbox status (this authoring environment)

- **Step 0 (download): BLOCKED here, not by copyright.** This sandbox's
  web-fetch policy forbids retrieving URLs via curl/wget/python, and the
  sanctioned WebFetch tool cannot return an 85 MB binary. kayin.moe is
  reachable at the network level, and the user (repo owner) authorized the
  download — but the fetch method is disallowed in this environment, so
  the file cannot be staged here. Run Step 0 on the provisioned machine.
- **Step 2 (CTFAK 2.0): ABSENT.** No .NET runtime (`dotnet`/`mono` not
  installed) and `IWG_CTFAK_DIR` is unset, so the external dump producer
  cannot run here regardless of the file.
- **What IS verified here:** the registry byte-verify logic and the
  `normalize_dump` normalizer + fail-closed coverage ledger, exercised on
  a SYNTHETIC `ctfak-inventory-dump/1` (`tests/test_mfa2pack_spike.py`,
  `tests/test_source_registry.py`, 15 tests). Per the milestone
  instruction, a synthetic dump + schema contract is **NOT** a successful
  extraction — it proves the consumer half of the pipeline, not that the
  real file was dumped and normalized. Steps 0–3 above are the actual
  extraction and have not run.
