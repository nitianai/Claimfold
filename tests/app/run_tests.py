#!/usr/bin/env python3
"""App (Research Council) test runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
APP_LIB = ROOT / "apps" / "research_council" / "lib"
APP_TESTS = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT / "platform"))
sys.path.insert(0, str(APP_LIB))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(APP_TESTS))

TEST_FILES = sorted(APP_TESTS.glob("test_*.py"))


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
    print(f"\n{ran} ran, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())