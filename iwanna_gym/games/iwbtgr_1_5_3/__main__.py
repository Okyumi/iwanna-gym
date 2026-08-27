"""CLI: python -m iwanna_gym.games.iwbtgr_1_5_3 build <source_root>"""
from __future__ import annotations

import argparse
import json

from . import build


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="iwbtgr_1_5_3")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="convert a locally supplied source tree "
                                     "into the compiled game pack")
    b.add_argument("source_root")
    b.add_argument("--out-dir")
    b.add_argument("--no-graph", action="store_true",
                   help="do not rewrite the committed room_graph.json")
    args = ap.parse_args(argv)
    summary = build(args.source_root, out_dir=args.out_dir,
                    write_graph=not args.no_graph)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
