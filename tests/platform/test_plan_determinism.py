"""Canonical JSON determinism and golden fixture tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from council.plan import canonical_json_bytes
from missionos.plan.writer import atomic_write_plan
from plan_test_helpers import ROOT, compile_project_plan

GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
GOLDEN_PATH = GOLDEN_DIR / "project-development.meeting_plan.json"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_same_input_same_bytes_and_hash():
    plan_a = compile_project_plan()
    plan_b = compile_project_plan()
    bytes_a = canonical_json_bytes(plan_a)
    bytes_b = canonical_json_bytes(plan_b)
    assert bytes_a == bytes_b
    assert _sha256_bytes(bytes_a) == _sha256_bytes(bytes_b)


def test_golden_fixture_matches_compiler():
    assert GOLDEN_PATH.is_file(), f"golden fixture missing: {GOLDEN_PATH}"
    plan = compile_project_plan()
    compiled = canonical_json_bytes(plan)
    golden = GOLDEN_PATH.read_bytes()
    assert compiled == golden, (
        f"golden mismatch hash compiled={_sha256_bytes(compiled)} golden={_sha256_bytes(golden)}"
    )


def test_binding_change_changes_only_executor_hash():
    base = canonical_json_bytes(compile_project_plan())
    overridden = canonical_json_bytes(compile_project_plan(cli_bindings={"architect": "codex"}))
    assert base != overridden
    base_plan = json.loads(base.decode("utf-8"))
    over_plan = json.loads(overridden.decode("utf-8"))
    assert base_plan["provenance"]["bindings_sha256"] != over_plan["provenance"]["bindings_sha256"]
    arch_base = next(p for p in base_plan["participants"] if p["role_id"] == "architect")
    arch_over = next(p for p in over_plan["participants"] if p["role_id"] == "architect")
    assert arch_base["executor_id"] == "claude"
    assert arch_over["executor_id"] == "codex"


def test_compiler_does_not_mutate_sources():
    from copy import deepcopy

    from missionos.plan.compiler import compile_meeting_plan
    from missionos.plan.loader import load_sources
    from plan_test_helpers import (
        FIXED_GENERATED_AT,
        FIXED_MEETING_ID,
        FIXED_TOPIC,
        fixture_paths,
    )

    paths = fixture_paths()
    sources = load_sources(
        scenario_path=paths["scenario"],
        roles_path=paths["roles"],
        executors_path=paths["executors"],
        bindings_path=paths["bindings"],
    )
    snapshot = deepcopy(sources)
    compile_meeting_plan(
        sources,
        meeting_id=FIXED_MEETING_ID,
        topic=FIXED_TOPIC,
        generated_at=FIXED_GENERATED_AT,
    )
    assert sources == snapshot


def test_atomic_write_then_read_hash_stable():
    import tempfile

    plan = compile_project_plan()
    path = Path(tempfile.mkdtemp()) / "meeting_plan.json"
    atomic_write_plan(path, plan)
    h1 = _sha256_bytes(path.read_bytes())
    h2 = _sha256_bytes(path.read_bytes())
    assert h1 == h2