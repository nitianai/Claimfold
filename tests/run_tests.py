#!/usr/bin/env python3
"""Backward-compatible wrapper — platform tests moved to tests/platform/."""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "platform" / "run_tests.py"
    raise SystemExit(runpy.run_path(str(target), run_name="__main__") or 0)