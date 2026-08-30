"""Content checksums for the frozen iwbtgr_1_5_3_v1 pack.

Two layers of pinning, per gameplay room:

  pack side    a digest of the runtime room content at load (pixel
               dimensions, the tile grid, sorted solid rects, sorted
               killer rects, the entity table) — recomputed from the
               live engine every run and compared to the frozen
               fixture; any engine/pack change that alters world
               content fails here until the freeze is re-recorded
  source side  a digest of the source room directory (room.txt,
               instances.txt, creation codes) — verified whenever the
               gm82save tree is available, proving the pack was built
               from the recorded source revision

Plus the global identities from the v1 manifest: the source tree
checksum, the pack file checksum, and the pack version string.

Regenerate the fixture with scripts/audit_iwbtgr_source.py after an
INTENTIONAL content change, then update manifests/iwbtgr_1_5_3_v1.toml.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os

import pytest

from iwanna_gym.clib import CIWanna
from iwanna_gym.games import iwbtgr_1_5_3 as G

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "iwbtgr_content_checksums.json")
MANIFEST = os.path.join(HERE, "..", "manifests", "iwbtgr_1_5_3_v1.toml")
SRC = os.environ.get("IWBTGR_SRC", "/tmp/iwbtgr-mod/IWBTGR Source Files")

needs_pack = pytest.mark.skipif(not os.path.isfile(G.PACK_PATH),
                                reason="iwbtgr pack not built locally")


def _audit_mod():
    spec = importlib.util.spec_from_file_location(
        "audit_iwbtgr_source",
        os.path.join(HERE, "..", "scripts", "audit_iwbtgr_source.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture():
    assert os.path.isfile(FIXTURE), "content-checksum fixture missing"
    return json.load(open(FIXTURE))


def _manifest_text():
    assert os.path.isfile(MANIFEST), "v1 manifest missing"
    return open(MANIFEST).read()


@needs_pack
def test_pack_room_content_checksums():
    """Every gameplay room's runtime content digest matches the frozen
    v1 fixture."""
    mod = _audit_mod()
    fix = _fixture()
    names = G.room_names()
    pack = G.load_pack()
    bad = []
    for rname, want in sorted(fix.items()):
        c = CIWanna.from_pack(pack, seed=11, checkpoint_respawn=True,
                              start_room=names.index(rname),
                              max_steps=200000)
        c.reset()
        got = mod.pack_room_sha(c)
        c.close()
        if got != want["pack_content_sha256"]:
            bad.append((rname, want["pack_content_sha256"][:12], got[:12]))
    assert not bad, f"room content drift: {bad}"


def test_source_room_checksums():
    """Source room directories hash to the recorded values (proof the
    pack matches the recorded source revision).  Skipped when the
    gm82save tree is not present."""
    if not os.path.isdir(os.path.join(SRC, "rooms")):
        pytest.skip("source tree not available")
    mod = _audit_mod()
    fix = _fixture()
    bad = []
    for rname, want in sorted(fix.items()):
        got = mod.source_room_sha(os.path.join(SRC, "rooms", rname))
        if got != want["source_sha256"]:
            bad.append((rname, want["source_sha256"][:12], got[:12]))
    assert not bad, f"source tree drift: {bad}"


@needs_pack
def test_manifest_identities():
    """The v1 manifest's identities match the built artifacts: pack
    file sha, source tree sha, pack version, importer version."""
    text = _manifest_text()
    h = hashlib.sha256(open(G.PACK_PATH, "rb").read()).hexdigest()
    assert h in text, "pack sha256 not recorded in the manifest"
    g = json.load(open(os.path.join(
        os.path.dirname(G.PACK_PATH), "iwbtgr_1_5_3.iwgame.json")))
    prov = g["provenance"]
    assert prov["source_checksum_sha256"] in text
    assert prov["pack_version"] == "iwbtgr_1_5_3_v1"
    assert 'pack_version = "iwbtgr_1_5_3_v1"' in text
    assert prov["importer_version"] in text


@needs_pack
def test_room_count_and_names_frozen():
    """The frozen pack carries exactly the 27 source rooms in source
    order, 20 of them gameplay rooms (all in the fixture)."""
    names = G.room_names()
    assert len(names) == 27
    fix = _fixture()
    assert len(fix) == 20
    assert set(fix) <= set(names)
