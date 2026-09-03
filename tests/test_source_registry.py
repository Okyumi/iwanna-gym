from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.iwimport.source_registry import (
    SourceRegistrationError,
    SourceSpec,
    register_source,
)


def _spec(data: bytes) -> SourceSpec:
    return SourceSpec(
        game_id="fixture",
        filename="source.mfa",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        canonical_url="https://example.invalid/source.mfa",
    )


def test_registers_verified_source_without_copying_it(tmp_path: Path):
    data = b"synthetic source fixture"
    source = tmp_path / "source.mfa"
    source.write_bytes(data)
    registry = tmp_path / "registry" / "source.json"

    record = register_source(source, registry, _spec(data))

    assert record["source_path"] == str(source.resolve())
    assert json.loads(registry.read_text())["sha256"] == _spec(data).sha256
    assert list(tmp_path.rglob("*.mfa")) == [source]


@pytest.mark.parametrize("failure", ["name", "size", "hash"])
def test_rejects_any_identity_mismatch_without_writing_record(
        tmp_path: Path, failure: str):
    data = b"canonical"
    source = tmp_path / ("wrong.mfa" if failure == "name" else "source.mfa")
    source.write_bytes(data if failure != "size" else data + b"x")
    spec = _spec(data)
    if failure == "hash":
        spec = SourceSpec(spec.game_id, spec.filename, spec.size, "0" * 64,
                          spec.canonical_url)
    registry = tmp_path / "registry.json"

    with pytest.raises(SourceRegistrationError):
        register_source(source, registry, spec)

    assert not registry.exists()


def test_canonical_pin_matches_manifest():
    manifest = Path("third_party/classic_source_manifest.toml").read_text()
    assert "c41928c4e6599b3535c7a1d0d4b0df4da6068184e037a899af4282b460678f76" in manifest
    assert "source_size_bytes = 85300282" in manifest
