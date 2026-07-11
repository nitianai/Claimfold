"""Single implementation checks (enabled after Phase 1 ledger extraction)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _find_function_defs(directory: Path, name: str) -> list[Path]:
    hits: list[Path] = []
    if not directory.is_dir():
        return hits
    for path in directory.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                hits.append(path)
    return hits


def test_append_event_single_implementation():
    store = ROOT / "platform" / "missionos" / "ledger" / "store.py"
    assert store.is_file(), "Phase 1 requires missionos.ledger.store"

    platform_hits = _find_function_defs(ROOT / "platform" / "missionos", "append_event")
    lib_hits = _find_function_defs(ROOT / "apps" / "research_council" / "lib", "append_event")

    real_impl = [
        p for p in platform_hits + lib_hits if "shim" not in p.name and p.name != "protocols.py"
    ]
    assert len(real_impl) == 1, f"expected one append_event impl, found: {real_impl}"
    assert real_impl[0] == store.resolve(), f"append_event must live in {store}"


test_append_event_single_implementation.__skip_phase0__ = False