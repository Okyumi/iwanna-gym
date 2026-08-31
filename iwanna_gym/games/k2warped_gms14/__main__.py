"""CLI: python -m iwanna_gym.games.k2warped_gms14 build <source-dir>"""
from __future__ import annotations

import argparse
import sys

from . import build


def main(argv=None):
    ap = argparse.ArgumentParser(prog="k2warped_gms14")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="convert the K2W GMS1.4 tree to a pack")
    b.add_argument("source_root")
    b.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "build":
        build(args.source_root, out_dir=args.out_dir)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
