"""mfa2pack feasibility-spike tests — synthetic, metadata-only.

Every fixture below is invented for these tests (fake frame/object
names, arbitrary coordinates and numbers); no third-party expressive
content is present.  The tests pin the spike's contracts:

  - the ctfak-inventory-dump/1 schema validation,
  - normalization with per-record provenance back to MFA identities,
  - the fail-closed coverage gate (unsupported / gameplay-relevant
    unknown records raise; cosmetic unknowns pass and are reported),
  - the registration gate in front of any CTFAK invocation,
  - the pinned external-CTFAK resolution rules.
"""
from __future__ import annotations

import json
import os

import pytest

from tools.importers.iwbtg_mfa import (CTFAK_COMMIT, CoverageError,
                                       CtfakUnavailable, DumpFormatError,
                                       RegistrationRequired,
                                       ctfak_invocation, normalize_dump,
                                       report_text,
                                       require_registered_source)
from tools.iwimport.source_registry import IWBTG_ORIGINAL


def synthetic_dump() -> dict:
    """A tiny, fully synthetic inventory dump exercising every record
    kind the normalizer supports."""
    return {
        "dump_format": "ctfak-inventory-dump/1",
        "ctfak_commit": CTFAK_COMMIT,
        "source_sha256": "0" * 64,
        "app": {
            "name": "SyntheticTestApp",
            "mfa_version": 6, "mfa_subversion": 3,
            "build_version": 283, "product": 2,
            "window": [640, 480],
            "frame_order": [10, 20],
            "global_values": [{"index": 0, "value": 3},
                              {"index": 1, "value": -1.5}],
            "global_strings": [{"index": 0, "value": "alpha"}],
        },
        "objects": [
            {"handle": 100, "name": "TestHero", "type_id": 2,
             "type_name": "Active", "loader_kind": "MFAActive",
             "qualifiers": [7], "group": "heroes",
             "movements": [
                 {"name": "walk", "type_id": 9, "type_name": "Platform",
                  "player": 1, "moving_at_start": 1,
                  "direction_at_start": 0,
                  "params": {"speed": 42, "acceleration": 7}}],
             },
            {"handle": 101, "name": "TestCounterThing", "type_id": 7,
             "type_name": "Counter", "loader_kind": "MFACounter",
             "counter": {"initial": 5, "min": 0, "max": 99}},
            {"handle": 102, "name": "TestGadget", "type_id": 32,
             "type_name": "Extension", "loader_kind":
                 "MFAExtensionObject"},
        ],
        "extensions": [{"handle": 1, "name": "kcpica.mfx",
                        "subtype": None}],
        "frames": [
            {"handle": 10, "name": "First Screen", "size": [640, 480],
             "layers": 2,
             "transitions": {"fade_in": {"module": "cctrans",
                                         "name": "door",
                                         "duration": 500}},
             "instances": [
                 {"instance_id": 1, "object_handle": 100,
                  "x": 32, "y": 416, "layer": 1, "flags": 0},
                 {"instance_id": 2, "object_handle": 101,
                  "x": 600, "y": 16, "layer": 2, "flags": 0}],
             "events": {"groups": [
                 {"identifier": 900, "flags": 0, "restricted": 0,
                  "is_group_marker": True, "container": None,
                  "conditions": [
                      {"num": -1, "object_type": -1,
                       "expressions": []}],
                  "actions": []},
                 {"identifier": 901, "flags": 0, "restricted": 0,
                  "container": 900,
                  "conditions": [
                      {"num": 3, "object_type": 2,
                       "object_handle": 100,
                       "expressions": [{"kind": "const", "value": 5}]}],
                  "actions": [
                      {"num": 12, "object_type": 7,
                       "object_handle": 101,
                       "expressions": [
                           {"kind": "global_value", "index": 0},
                           {"kind": "const", "value": 1}]}]},
             ]}},
            {"handle": 20, "name": "Second Screen", "size": [800, 600],
             "instances": [
                 {"instance_id": 3, "object_handle": 102,
                  "x": 0, "y": 0}],
             "events": {"groups": []}},
        ],
        "unknown_chunks": [
            {"where": "app", "chunk_id": "AGMI", "size": 12345},
        ],
        "unsupported": [],
    }


def test_normalize_counts_and_provenance():
    inv = normalize_dump(synthetic_dump())
    c = inv["counts"]
    assert c["frames"] == 2
    assert c["objects"] == 3
    assert c["instances"] == 3
    assert c["event_groups"] == 2
    assert c["conditions"] == 2
    assert c["actions"] == 1
    assert c["expressions"] == 3
    assert c["movements"] == 1
    assert c["counters"] == 1
    assert c["extensions"] == 1
    assert c["transitions"] == 1
    assert c["global_values"] == 2 and c["global_strings"] == 1
    assert c["qualifier_links"] == 1
    assert c["nested_groups"] == 1
    assert c["unknown_chunks_cosmetic"] == 1
    assert c["unknown_chunks_gameplay"] == 0
    # provenance round-trips to MFA identities
    f0 = inv["frames"][0]
    assert f0["provenance"] == {"mfa_frame_handle": 10,
                                "mfa_frame_name": "First Screen"}
    inst = f0["instances"][0]
    assert inst["provenance"]["mfa_instance_id"] == 1
    assert inst["provenance"]["mfa_object_handle"] == 100
    assert inst["object_name"] == "TestHero"
    act = f0["events"]["groups"][1]["actions"][0]
    assert act["provenance"] == {"mfa_frame_handle": 10,
                                 "event_group_index": 1,
                                 "atom_kind": "actions",
                                 "atom_ordinal": 0}
    # nested-group linkage preserved
    assert f0["events"]["groups"][1]["container"] == 900
    assert "coverage: PASS" in report_text(inv)


def test_gameplay_relevant_unknown_chunk_fails_closed():
    d = synthetic_dump()
    d["unknown_chunks"].append(
        {"where": "frames[10]", "chunk_id": "XQZZ", "size": 64})
    with pytest.raises(CoverageError) as e:
        normalize_dump(d)
    assert "XQZZ" in str(e.value)


def test_unparsed_object_fails_closed():
    d = synthetic_dump()
    d["objects"][0]["unparsed"] = True
    with pytest.raises(CoverageError):
        normalize_dump(d)


def test_dumper_unsupported_record_fails_closed():
    d = synthetic_dump()
    d["unsupported"].append({"where": "frames[20]/events",
                             "note": "qualifier list truncated"})
    with pytest.raises(CoverageError):
        normalize_dump(d)


def test_event_atom_missing_identity_fails_closed():
    d = synthetic_dump()
    del d["frames"][0]["events"]["groups"][1]["actions"][0]["num"]
    with pytest.raises(CoverageError) as e:
        normalize_dump(d)
    assert "missing num/object_type" in str(e.value)


def test_dangling_references_fail_closed():
    d = synthetic_dump()
    d["frames"][0]["instances"][0]["object_handle"] = 999
    with pytest.raises(CoverageError):
        normalize_dump(d)
    d = synthetic_dump()
    d["app"]["frame_order"] = [10, 20, 99]
    with pytest.raises(CoverageError):
        normalize_dump(d)


def test_wrong_dump_format_rejected():
    d = synthetic_dump()
    d["dump_format"] = "ctfak-inventory-dump/999"
    with pytest.raises(DumpFormatError):
        normalize_dump(d)


def test_registration_gate_blocks_unregistered():
    import pathlib
    import tempfile
    td = pathlib.Path(tempfile.mkdtemp(prefix="mfa_spike_"))
    fake = td / "iwbtgbeta(fs).mfa"
    fake.write_bytes(b"not the real file")
    reg = td / "registry.json"
    with pytest.raises(RegistrationRequired):
        require_registered_source(fake, registry=reg)
    # a forged record that does not match the pinned spec also fails
    reg.write_text(json.dumps({"sha256": "f" * 64, "size": 17,
                               "source_path": str(fake)}))
    with pytest.raises(RegistrationRequired):
        require_registered_source(fake, registry=reg)


def test_ctfak_invocation_requires_registration_and_install():
    import pathlib
    import tempfile
    td = pathlib.Path(tempfile.mkdtemp(prefix="mfa_spike_"))
    fake = td / "iwbtgbeta(fs).mfa"
    fake.write_bytes(b"x")
    with pytest.raises(RegistrationRequired):
        ctfak_invocation(fake, td, registry=td / "none.json")
    # with a (synthetically) satisfied registration record, the gate
    # still refuses: the bytes no longer match the pin (reverify) and
    # no external CTFAK install exists — both are refusals, never
    # silent passes
    reg = td / "reg.json"
    reg.write_text(json.dumps({
        "sha256": IWBTG_ORIGINAL.sha256, "size": IWBTG_ORIGINAL.size,
        "source_path": str(fake)}))
    old = os.environ.pop("IWG_CTFAK_DIR", None)
    try:
        with pytest.raises((RegistrationRequired, CtfakUnavailable)):
            ctfak_invocation(fake, td, registry=reg)
    finally:
        if old is not None:
            os.environ["IWG_CTFAK_DIR"] = old


def test_pinned_ctfak_identity():
    assert CTFAK_COMMIT == "f38ba7951f5fa9d714dc5d97772882ea6aa61717"
    assert IWBTG_ORIGINAL.sha256 == ("c41928c4e6599b3535c7a1d0d4b0df4d"
                                     "a6068184e037a899af4282b460678f76")
    assert IWBTG_ORIGINAL.size == 85_300_282
