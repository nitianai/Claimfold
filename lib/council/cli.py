#!/usr/bin/env python3
"""CLI entry: argparse routing into council handlers."""
from __future__ import annotations

from utils import set_relax_cli

from council import build_parser, get_handlers


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "relax", False):
        set_relax_cli(True)
    get_handlers()[args.command](args)


if __name__ == "__main__":
    main()
