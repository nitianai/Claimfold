#!/usr/bin/env python3
"""DEPRECATED — Phase 1 split script (do not re-run).

This script previously rewrote lib/council/* from lib/engine.py. Re-running it
would overwrite hand-maintained modules and reintroduce structural drift.

Edit lib/council/* directly. See scripts/split_core.py for the same policy.
"""
from __future__ import annotations

import sys

_DEPRECATION = """
ERROR: scripts/split_engine.py is deprecated and disabled.

Reason: one-shot split scripts must not overwrite the current council package.
Do not re-run. Edit lib/council/* directly.
"""


def main() -> None:
    print(_DEPRECATION.strip(), file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()