#!/usr/bin/env python3
"""Compare meeting quality metrics across experiment runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEETINGS_DIR = ROOT / "meetings"
sys.path.insert(0, str(ROOT / "lib"))

from meeting_quality import compare_reports  # noqa: E402


def resolve_meeting(path_or_id: str) -> Path:
    p = Path(path_or_id)
    if p.exists():
        return p.resolve()
    candidate = MEETINGS_DIR / path_or_id
    if candidate.exists():
        return candidate.resolve()
    if not path_or_id.startswith("meet-"):
        candidate = MEETINGS_DIR / f"meet-{path_or_id}"
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(path_or_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Claimfold meeting experiments")
    parser.add_argument("meetings", nargs="+", help="Meeting ids or paths under meetings/")
    parser.add_argument("-o", "--output", help="Write markdown report to file")
    args = parser.parse_args()

    dirs: list[Path] = []
    for m in args.meetings:
        try:
            dirs.append(resolve_meeting(m))
        except FileNotFoundError:
            raise SystemExit(f"Meeting not found: {m}") from None

    report = compare_reports(*dirs)
    if args.output:
        out = Path(args.output)
        out.write_text(report + "\n", encoding="utf-8")
        print(f"Wrote: {out}")
    else:
        print(report)


if __name__ == "__main__":
    main()