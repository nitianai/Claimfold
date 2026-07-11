#!/usr/bin/env python3
"""One-shot helper: verify council package imports after split."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

import engine  # noqa: E402

REQUIRED = (
    "invoke_cli",
    "merge_guest_json_into_state",
    "load_state",
    "save_state",
    "run_one_parallel_round",
    "main",
    "build_parser",
)

missing = [name for name in REQUIRED if not hasattr(engine, name)]
if missing:
    print("missing exports:", missing)
    raise SystemExit(1)
print("engine exports ok:", ", ".join(REQUIRED))