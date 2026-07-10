#!/usr/bin/env python3
"""Minimal test runner (no pytest required)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

TEST_FILES = [
    ROOT / "tests" / "test_utils.py",
    ROOT / "tests" / "test_claim_lifecycle.py",
    ROOT / "tests" / "test_mock_filter.py",
    ROOT / "tests" / "test_strict_default.py",
    ROOT / "tests" / "test_engine_regression.py",
    ROOT / "tests" / "test_config_paths.py",
    ROOT / "tests" / "test_plan_compiler.py",
    ROOT / "tests" / "test_plan_schema.py",
    ROOT / "tests" / "test_plan_semantics.py",
    ROOT / "tests" / "test_plan_reader.py",
    ROOT / "tests" / "test_plan_determinism.py",
    ROOT / "tests" / "test_scenario_start.py",
]


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ran = failed = 0
    for path in TEST_FILES:
        mod = load_module(path)
        for name in sorted(dir(mod)):
            if not name.startswith("test_"):
                continue
            ran += 1
            try:
                getattr(mod, name)()
                print(f"ok {path.name}::{name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {path.name}::{name}: {exc}")
    print(f"\n{ran} tests, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())