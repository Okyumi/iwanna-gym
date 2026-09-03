"""External CTFAK 2.0 invocation for the registered original-IWBTG .mfa.

CTFAK 2.0 is AGPL-3.0.  This repo (MIT) NEVER vendors, copies, or links
its code: CTFAK runs as a separate process from a user-managed external
install, and this module only (a) verifies the pinned revision,
(b) refuses to touch any source file that has not passed the strict
registration gate, and (c) constructs the documented command line.

Pinned revision (docs/iwbtg_mfa_feasibility.md has the full procedure):

    repo    https://github.com/CTFAK/CTFAK2.0
    branch  master  (the README-recommended CTFAK 2.2 line)
    commit  f38ba7951f5fa9d714dc5d97772882ea6aa61717

Environment:
    IWG_CTFAK_DIR   the external CTFAK checkout/build directory
                    (never inside this repository)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tools.iwimport.source_registry import (IWBTG_ORIGINAL, SourceSpec,
                                            sha256_file)

CTFAK_REPO = "https://github.com/CTFAK/CTFAK2.0"
CTFAK_COMMIT = "f38ba7951f5fa9d714dc5d97772882ea6aa61717"
DEFAULT_REGISTRY = os.path.join("build", "source_registry",
                                "iwbtg_original_2007.json")

#: the InventoryDump tool name the external AGPL plugin registers under
INVENTORY_TOOL = "InventoryDump"


class RegistrationRequired(RuntimeError):
    """The .mfa has not passed the strict registration gate."""


class CtfakUnavailable(RuntimeError):
    """No usable external CTFAK install was found."""


def require_registered_source(source: str | Path,
                              registry: str | Path = DEFAULT_REGISTRY,
                              spec: SourceSpec = IWBTG_ORIGINAL,
                              reverify: bool = True) -> dict:
    """Refuse to proceed unless *source* is the registered canonical
    file: the local registration record must exist, match the pinned
    spec, and (reverify=True) the file must still hash to the pin."""
    reg = Path(registry)
    if not reg.is_file():
        raise RegistrationRequired(
            f"no registration record at {reg}; run\n"
            f"  python -m tools.iwimport register-iwbtg "
            f"'{spec.filename}'\nfirst (the command refuses any "
            f"filename/size/sha256 mismatch)")
    record = json.loads(reg.read_text(encoding="utf-8"))
    if record.get("sha256") != spec.sha256 or \
            record.get("size") != spec.size:
        raise RegistrationRequired(
            f"registration record at {reg} does not match the pinned "
            f"canonical spec — re-run register-iwbtg")
    src = Path(source).expanduser().resolve()
    if str(src) != record.get("source_path"):
        raise RegistrationRequired(
            f"{src} is not the registered source path "
            f"({record.get('source_path')})")
    if reverify:
        if src.stat().st_size != spec.size or \
                sha256_file(src) != spec.sha256:
            raise RegistrationRequired(
                f"{src} no longer matches the pinned bytes — refusing")
    return record


def resolve_ctfak(ctfak_dir: str | None = None) -> Path:
    """Locate the external CTFAK install and verify the pinned commit
    when the directory is a git checkout."""
    d = Path(ctfak_dir or os.environ.get("IWG_CTFAK_DIR", "")).expanduser()
    if not d or not d.is_dir():
        raise CtfakUnavailable(
            "set IWG_CTFAK_DIR to an external CTFAK 2.0 checkout/build "
            f"(clone {CTFAK_REPO} at {CTFAK_COMMIT[:12]}; build per "
            "docs/iwbtg_mfa_feasibility.md). CTFAK is AGPL and must "
            "live outside this repository")
    if (d / ".git").exists():
        head = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              timeout=20).stdout.strip()
        if head != CTFAK_COMMIT:
            raise CtfakUnavailable(
                f"CTFAK checkout at {d} is at {head[:12]}, expected the "
                f"pinned {CTFAK_COMMIT[:12]}")
    return d


def ctfak_invocation(source: str | Path, out_dir: str | Path,
                     ctfak_dir: str | None = None,
                     registry: str | Path = DEFAULT_REGISTRY
                     ) -> list[str]:
    """The documented, reproducible CTFAK command line for the
    registered source.  Raises rather than guessing when the gate or
    the external install is missing."""
    require_registered_source(source, registry=registry)
    d = resolve_ctfak(ctfak_dir)
    cli = None
    for cand in ("Interface/CTFAK.Cli/bin/Release/net6.0/CTFAK.Cli.dll",
                 "Interface/CTFAK.Cli/bin/Release/net6.0-windows/"
                 "CTFAK.Cli.dll",
                 "CTFAK.Cli.dll"):
        if (d / cand).is_file():
            cli = d / cand
            break
    if cli is None:
        raise CtfakUnavailable(
            f"no built CTFAK.Cli.dll under {d}; build the pinned "
            f"revision first (dotnet build -c Release, see the "
            f"feasibility doc)")
    return ["dotnet", str(cli),
            "-path", str(Path(source).resolve()),
            "-tool", INVENTORY_TOOL,
            "-out", str(Path(out_dir).resolve())]


def run_ctfak(source: str | Path, out_dir: str | Path,
              ctfak_dir: str | None = None,
              registry: str | Path = DEFAULT_REGISTRY,
              timeout: int = 1800) -> Path:
    """Run the external CTFAK InventoryDump; returns the dump JSON path."""
    cmd = ctfak_invocation(source, out_dir, ctfak_dir, registry)
    os.makedirs(out_dir, exist_ok=True)
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout)
    if proc.returncode != 0:
        raise CtfakUnavailable(
            f"CTFAK exited {proc.returncode}:\n{proc.stderr[-2000:]}")
    dump = Path(out_dir) / "inventory_dump.json"
    if not dump.is_file():
        raise CtfakUnavailable(
            f"CTFAK produced no {dump.name} in {out_dir}")
    return dump
