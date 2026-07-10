#!/usr/bin/env python3
"""DEPRECATED — Phase 2 split script (do not re-run).

This script previously split lib/council/core.py and injected a blanket SHARED
import block into every output module. That pattern was removed in the P0
dependency cleanup (2026-07): modules must declare their own minimal imports.

Re-running this script would overwrite hand-maintained modules and reintroduce
false dependencies. Use manual edits or targeted refactor scripts instead.
"""
from __future__ import annotations

import sys

_DEPRECATION = """
ERROR: scripts/split_core.py is deprecated and disabled.

Reason: SHARED import injection polluted module dependency surfaces.
See Dependency Architecture Review — P0 cleanup.

Do not re-run. Edit lib/council/* directly.
"""


def main() -> None:
    print(_DEPRECATION.strip(), file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()