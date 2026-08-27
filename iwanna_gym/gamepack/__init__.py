"""Canonical game representation (".iwgame.json") and compiled runtime
packs (".iwpack") — see docs/gamepack_format.md and
docs/importer_architecture.md.

Pipeline (all offline; nothing here runs during stepping):

    source project --extractor--> .iwgame.json --compile--> .iwpack --> C core
"""
from .schema import (
    FORMAT_VERSION,
    MAPPING_STATUSES,
    PHYSICS_PROFILES,
    ACTION_PROFILES,
    ENTITY_KINDS,
    EVENT_WHEN,
    EVENT_ACTIONS,
    new_gamepack,
    load_iwgame,
    save_iwgame,
)
from .validate import ValidationReport, validate
from .compilepack import compile_pack, PACK_MAGIC
from .report import mapping_report

__all__ = [
    "FORMAT_VERSION", "MAPPING_STATUSES", "PHYSICS_PROFILES",
    "ACTION_PROFILES", "ENTITY_KINDS", "EVENT_WHEN", "EVENT_ACTIONS",
    "new_gamepack", "load_iwgame", "save_iwgame",
    "ValidationReport", "validate", "compile_pack", "PACK_MAGIC",
    "mapping_report",
]
