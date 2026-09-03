"""iwimport — the offline game-import pipeline CLI.

    python -m tools.iwimport inspect  <source_dir>
    python -m tools.iwimport convert  <source_dir> -o game.iwgame.json [--game ID]
    python -m tools.iwimport validate <game.iwgame.json> [--allow-unsupported]
    python -m tools.iwimport compile  <game.iwgame.json> -o game.iwpack [--allow-unsupported]
    python -m tools.iwimport report   <game.iwgame.json>
    python -m tools.iwimport register-iwbtg /path/to/iwbtgbeta(fs).mfa

See docs/importer_architecture.md for the full workflow.
"""
from __future__ import annotations

import argparse
import sys

from iwanna_gym.gamepack import (
    compile_pack,
    load_iwgame,
    mapping_report,
    save_iwgame,
    validate,
)
from iwanna_gym.gamepack.compilepack import CompileError
from tools import importers


def _resolve_importer(args):
    if args.importer:
        return importers.get_importer(args.importer)
    mod = importers.detect_importer(args.source)
    if mod is None:
        sys.exit(f"error: no importer recognizes {args.source!r} "
                 f"(available: {importers.available()}); pass --importer")
    return mod


def cmd_inspect(args) -> int:
    mod = _resolve_importer(args)
    doc = mod.extract(args.source, game_id=args.game)
    print(mapping_report(doc))
    rep = validate(doc, allow_unsupported=True)
    n_bad = len(rep.unsupported)
    print(f"\ninspect: importer={mod.NAME} v{mod.VERSION}; "
          f"{len(doc['rooms'])} rooms; "
          f"{n_bad} unmapped element(s)"
          + ("" if n_bad == 0 else " — convert/compile will fail without "
                                  "--allow-unsupported"))
    return 0


def cmd_convert(args) -> int:
    mod = _resolve_importer(args)
    doc = mod.extract(args.source, game_id=args.game)
    rep = validate(doc, allow_unsupported=args.allow_unsupported)
    print(rep.text())
    if not rep.ok:
        return 1
    out = args.output or (doc["metadata"]["game_id"] + ".iwgame.json")
    save_iwgame(doc, out)
    print(f"wrote {out}")
    return 0


def cmd_validate(args) -> int:
    doc = load_iwgame(args.iwgame)
    rep = validate(doc, allow_unsupported=args.allow_unsupported)
    print(rep.text())
    return 0 if rep.ok else 1


def cmd_compile(args) -> int:
    doc = load_iwgame(args.iwgame)
    try:
        res = compile_pack(doc, allow_unsupported=args.allow_unsupported)
    except CompileError as e:
        print(f"compile failed: {e}", file=sys.stderr)
        return 1
    out = args.output or (doc["metadata"]["game_id"] + ".iwpack")
    with open(out, "wb") as f:
        f.write(res.data)
    print(f"wrote {out}: {res.n_rooms} rooms, {res.size} bytes")
    if res.dropped:
        print("WARNING: pack is INCOMPLETE — dropped unmapped elements:")
        for d in res.dropped:
            print(f"  {d}")
    return 0


def cmd_report(args) -> int:
    print(mapping_report(load_iwgame(args.iwgame)))
    return 0


def cmd_inventory(args) -> int:
    """Source coverage inventory (currently: iwbtgr gm82save trees)."""
    from tools.importers import iwbtgr

    src = args.source
    if not iwbtgr.detect(src):
        sys.exit(f"error: {src!r} is not an IWBTGR gm82save source tree")
    root = iwbtgr.resolve_root(src)
    rep = iwbtgr.build_inventory(root, with_code=args.with_code)
    out = args.output or "build/source_reports/iwbtgr_1_5_3.json"
    iwbtgr.save_report(rep, out)
    c = rep["counts"]
    print(f"wrote {out}: {c['rooms']} rooms, "
          f"{c['object_definitions']} objects, "
          f"{c['object_instances']} instances, {c['tiles']} tiles")
    if args.docs:
        import os
        pairs = [("iwbtgr_source_inventory.md", iwbtgr.doc_source_inventory),
                 ("iwbtgr_object_mapping.md", iwbtgr.doc_object_mapping),
                 ("iwbtgr_room_inventory.md", iwbtgr.doc_room_inventory)]
        for fn, gen in pairs:
            p = os.path.join(args.docs, fn)
            with open(p, "w", encoding="utf-8") as f:
                f.write(gen(rep))
            print(f"wrote {p}")
    return 0


def cmd_register_iwbtg(args) -> int:
    """Verify and locally register Kayin's canonical original source."""
    from tools.iwimport.source_registry import (
        SourceRegistrationError,
        register_source,
    )

    try:
        record = register_source(args.source, args.registry)
    except SourceRegistrationError as exc:
        print(f"registration failed: {exc}", file=sys.stderr)
        return 1
    print(f"registered {record['game_id']}: {record['sha256']}")
    print(f"local record: {args.registry}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="iwimport", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inspect", help="extract a source and print the mapping report")
    p.add_argument("source")
    p.add_argument("--importer", help="force an importer instead of auto-detect")
    p.add_argument("--game", help="game_id override")
    p.set_defaults(fn=cmd_inspect)

    p = sub.add_parser("convert", help="source -> canonical .iwgame.json")
    p.add_argument("source")
    p.add_argument("-o", "--output")
    p.add_argument("--importer")
    p.add_argument("--game", help="game_id override")
    p.add_argument("--allow-unsupported", action="store_true")
    p.set_defaults(fn=cmd_convert)

    p = sub.add_parser("validate", help="validate a .iwgame.json")
    p.add_argument("iwgame")
    p.add_argument("--allow-unsupported", action="store_true")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("compile", help=".iwgame.json -> binary .iwpack")
    p.add_argument("iwgame")
    p.add_argument("-o", "--output")
    p.add_argument("--allow-unsupported", action="store_true",
                   help="drop unmapped elements VISIBLY (pack marked incomplete)")
    p.set_defaults(fn=cmd_compile)

    p = sub.add_parser("report", help="mapping/provenance report for a .iwgame.json")
    p.add_argument("iwgame")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("inventory",
                       help="machine-readable source inventory (iwbtgr)")
    p.add_argument("source", help="path to the source tree (user-supplied)")
    p.add_argument("-o", "--output")
    p.add_argument("--docs", help="also write the generated docs into this dir")
    p.add_argument("--with-code", action="store_true",
                   help="embed GML bodies (LOCAL inspection only — do not "
                        "commit the resulting file)")
    p.set_defaults(fn=cmd_inventory)

    p = sub.add_parser(
        "register-iwbtg",
        help="verify and locally register the canonical original IWBTG .mfa",
    )
    p.add_argument("source", help="path to user-fetched iwbtgbeta(fs).mfa")
    p.add_argument(
        "--registry",
        default="build/source_registry/iwbtg_original_2007.json",
        help="gitignored local metadata record",
    )
    p.set_defaults(fn=cmd_register_iwbtg)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
