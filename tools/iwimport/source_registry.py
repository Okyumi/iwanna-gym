"""Strict registration for non-redistributable, user-supplied sources."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Union


@dataclass(frozen=True)
class SourceSpec:
    game_id: str
    filename: str
    size: int
    sha256: str
    canonical_url: str


IWBTG_ORIGINAL = SourceSpec(
    game_id="iwbtg_original_2007",
    filename="iwbtgbeta(fs).mfa",
    size=85_300_282,
    sha256="c41928c4e6599b3535c7a1d0d4b0df4da6068184e037a899af4282b460678f76",
    canonical_url="https://kayin.moe/iwbtg/source/iwbtgbeta(fs).mfa",
)


class SourceRegistrationError(ValueError):
    """The supplied file is not the pinned canonical source."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_source(source: Union[str, Path], registry: Union[str, Path],
                    spec: SourceSpec = IWBTG_ORIGINAL) -> dict:
    """Verify *source* byte-for-byte and write only a local metadata record."""
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise SourceRegistrationError(f"source is not a file: {source_path}")
    if source_path.name != spec.filename:
        raise SourceRegistrationError(
            f"expected filename {spec.filename!r}, got {source_path.name!r}"
        )
    size = source_path.stat().st_size
    if size != spec.size:
        raise SourceRegistrationError(
            f"size mismatch: expected {spec.size} bytes, got {size}"
        )
    digest = sha256_file(source_path)
    if digest != spec.sha256:
        raise SourceRegistrationError(
            f"sha256 mismatch: expected {spec.sha256}, got {digest}"
        )

    record = {
        "schema_version": 1,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        **asdict(spec),
    }
    registry_path = Path(registry).expanduser()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record
