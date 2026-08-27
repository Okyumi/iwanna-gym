"""Human-readable mapping/provenance report for an IR document."""
from __future__ import annotations

from typing import Any

from .schema import iter_elements
from .validate import validate


def mapping_report(doc: dict[str, Any]) -> str:
    rep = validate(doc, allow_unsupported=True)
    md = doc.get("metadata", {})
    prov = doc.get("provenance", {})
    lines = []
    lines.append(f"game_id:  {md.get('game_id')}   title: {md.get('title', '')}")
    lines.append(f"source:   {prov.get('source_game')} {prov.get('source_version')} "
                 f"({prov.get('source_format')})")
    lines.append(f"importer: {prov.get('importer')} {prov.get('importer_version')}")
    if prov.get("source_checksum_sha256"):
        lines.append(f"checksum: sha256:{prov['source_checksum_sha256']}")
    lines.append(f"physics_profile: {doc.get('physics_profile')}   "
                 f"action_profile: {doc.get('action_profile')}")
    rooms = doc.get("rooms", [])
    lines.append(f"rooms: {len(rooms)}   start_room: "
                 f"{doc.get('room_graph', {}).get('start_room')}")
    for r in rooms:
        n_i = len(r.get("instances", []))
        n_e = len(r.get("events", []))
        edges = {k: v for k, v in r.get("edges", {}).items() if v is not None}
        lines.append(
            f"  [{r['id']}] {r.get('name')}: {r['width_tiles']}x{r['height_tiles']} "
            f"tiles, {n_i} instances, {n_e} events, "
            f"{len(r.get('warps', []))} warps, "
            f"{len(r.get('checkpoints', []))} checkpoints"
            + (f", edges={edges}" if edges else "")
            + (", goal" if (r.get("goal") or "G" in "".join(r.get("tiles", []))) else "")
        )
    lines.append("global_flags: " + (
        ", ".join(f"{f['id']}:{f.get('name')}" for f in doc.get("global_flags", []))
        or "none"))
    lines.append("mapping statuses: " + (
        ", ".join(f"{k}={v}" for k, v in sorted(rep.status_counts.items()))
        or "none"))
    bad = [(w, el) for w, el in iter_elements(doc)
           if el.get("mapping_status") in ("unsupported", "unknown")]
    if bad:
        lines.append("NOT mapped (blocked from compile without --allow-unsupported):")
        for w, el in bad:
            note = f" — {el.get('notes')}" if el.get("notes") else ""
            lines.append(f"  {el.get('mapping_status'):11s} {w}{note}")
    else:
        lines.append("all elements mapped (exact or documented-equivalent)")
    equiv = [(w, el) for w, el in iter_elements(doc)
             if el.get("mapping_status") == "equivalent"]
    if equiv:
        lines.append("documented equivalences:")
        for w, el in equiv:
            note = f" — {el.get('notes')}" if el.get("notes") else ""
            lines.append(f"  {w}{note}")
    return "\n".join(lines)
