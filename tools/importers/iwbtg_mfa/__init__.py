"""mfa2pack feasibility spike for the original IWBTG (.mfa, CTFAK 2.0).

Pipeline (every stage offline; CTFAK stays an EXTERNAL process — it is
AGPL-3.0 and is never vendored, copied, or linked into this MIT repo):

    iwbtgbeta(fs).mfa            (user-fetched; strictly registered by
        |                         `python -m tools.iwimport register-iwbtg`)
    CTFAK 2.0 @ pinned commit    (external install; InventoryDump plugin
        |                         emits ctfak-inventory-dump/1 JSON)
    normalize.py                 (this package: normalized, source-derived
        |                         inventory with per-record provenance)
    coverage gate                (fails closed on unsupported or unknown
                                  gameplay-relevant records)

This stage produces an auditable INVENTORY, not a playable pack, and it
makes no exactness claim about the original game.  See
docs/iwbtg_mfa_feasibility.md for the pinned CTFAK revision, the
reproducible install/invocation procedure, and the current
environmental gates.
"""
from __future__ import annotations

NAME = "iwbtg_mfa"

from .normalize import (DUMP_FORMAT, CoverageError, DumpFormatError,  # noqa: E402,F401
                        normalize_dump, report_text)
from .ctfak_runner import (CTFAK_COMMIT, CTFAK_REPO,  # noqa: E402,F401
                           CtfakUnavailable, RegistrationRequired,
                           ctfak_invocation, require_registered_source)
