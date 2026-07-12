"""Phase 5: minimal second app consumes missionos without council."""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SMOKE_ROOT = ROOT / "apps" / "platform_smoke"
SMOKE_PKG = SMOKE_ROOT / "platform_smoke"


def _load_smoke_modules():
    if str(SMOKE_ROOT) not in sys.path:
        sys.path.insert(0, str(SMOKE_ROOT))
    from platform_smoke.ledger_demo import run_ledger_demo
    from platform_smoke.plan_demo import compile_smoke_plan_summary

    return run_ledger_demo, compile_smoke_plan_summary


def test_platform_smoke_ledger_demo():
    run_ledger_demo, _ = _load_smoke_modules()
    with tempfile.TemporaryDirectory() as tmp:
        result = run_ledger_demo(Path(tmp), message="independence-check")
    assert result["count"] == 1
    assert result["last_event"] == "NOTE"


def test_platform_smoke_plan_compile():
    _, compile_smoke_plan_summary = _load_smoke_modules()
    summary = compile_smoke_plan_summary(ROOT)
    assert summary["schema_version"] == "1.0"
    assert summary["participants"] == 6


def test_platform_smoke_does_not_import_council():
    forbidden = ("council", "runtime_ext", "engine", "claim_lifecycle")
    for path in SMOKE_PKG.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in forbidden, f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    assert top not in forbidden, f"{path.name} imports from {node.module}"