#!/usr/bin/env python3
"""Platform / missionos test runner (Phase 0+)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PLATFORM = ROOT / "platform"
APP_LIB = ROOT / "apps" / "research_council" / "lib"
PLATFORM_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(PLATFORM))
sys.path.insert(0, str(APP_LIB))
sys.path.insert(0, str(PLATFORM_TESTS))

TEST_FILES = sorted((Path(__file__).parent).glob("test_*.py"))


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ran = failed = skipped = 0
    for path in TEST_FILES:
        mod = load_module(path)
        for name in sorted(dir(mod)):
            if not name.startswith("test_"):
                continue
            fn = getattr(mod, name)
            if getattr(fn, "__skip_phase0__", False):
                skipped += 1
                print(f"skip {path.name}::{name} (deferred)")
                continue
            ran += 1
            try:
                fn()
                print(f"ok {path.name}::{name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {path.name}::{name}: {exc}")
    print(f"\n{ran} ran, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())