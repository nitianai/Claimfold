"""Tests for compile_meeting_plan and load_sources."""

from __future__ import annotations

import copy
from pathlib import Path

from council.plan import compile_meeting_plan, load_sources
from council.plan.validators import PlanValidationError, validate_plan
from plan_test_helpers import (
    FIXTURES,
    SCENARIO,
    compile_project_plan,
    fixture_paths,
    FIXED_GENERATED_AT,
    FIXED_MEETING_ID,
    FIXED_TOPIC,
)


def test_compile_project_development_valid():
    plan = compile_project_plan()
    validate_plan(plan)
    assert plan["schema_version"] == "1.0"
    assert plan["meeting_id"] == FIXED_MEETING_ID
    assert len(plan["participants"]) == 6
    role_ids = {p["role_id"] for p in plan["participants"]}
    assert role_ids == {
        "moderator",
        "architect",
        "implementation_engineer",
        "test_reviewer",
        "adversarial_reviewer",
        "recorder",
    }
    assert "claude" not in str(plan["scenario"])
    assert plan["participants"][1]["role_id"] == "architect"
    assert plan["participants"][1]["executor_id"] == "claude"
    assert plan["participants"][1]["executor_snapshot"]["secret_refs"] == ["ANTHROPIC_API_KEY"]


def test_cli_binding_overrides_file():
    plan = compile_project_plan(cli_bindings={"architect": "codex"})
    architect = next(p for p in plan["participants"] if p["role_id"] == "architect")
    assert architect["executor_id"] == "codex"
    assert plan["provenance"]["bindings_source"] == "cli+file"


def test_missing_required_role_binding_fails():
    paths = fixture_paths()
    sources = load_sources(
        scenario_path=paths["scenario"],
        roles_path=paths["roles"],
        executors_path=paths["executors"],
        bindings_path=paths["bindings"],
    )
    sources = copy.deepcopy(sources)
    del sources["bindings"]["recorder"]
    try:
        compile_meeting_plan(
            sources,
            meeting_id=FIXED_MEETING_ID,
            topic=FIXED_TOPIC,
            generated_at=FIXED_GENERATED_AT,
        )
        raise AssertionError("expected PlanValidationError")
    except PlanValidationError as exc:
        assert "recorder" in str(exc)


def test_unknown_executor_binding_fails():
    try:
        compile_project_plan(cli_bindings={"architect": "no_such_executor"})
        raise AssertionError("expected PlanValidationError")
    except PlanValidationError as exc:
        assert "unknown executor" in str(exc)


def test_disabled_executor_fails():
    try:
        compile_project_plan(cli_bindings={"architect": "disabled_executor"})
        raise AssertionError("expected PlanValidationError")
    except PlanValidationError as exc:
        assert "disabled" in str(exc)


def test_scenario_implicit_executor_fails():
    paths = fixture_paths()
    sources = load_sources(
        scenario_path=paths["scenario"],
        roles_path=paths["roles"],
        executors_path=paths["executors"],
        bindings_path=paths["bindings"],
    )
    for bad_value in ("claude", "", {}):
        mutated = copy.deepcopy(sources)
        mutated["scenario"]["default_executor"] = bad_value
        try:
            compile_meeting_plan(
                mutated,
                meeting_id=FIXED_MEETING_ID,
                topic=FIXED_TOPIC,
                generated_at=FIXED_GENERATED_AT,
            )
            raise AssertionError("expected PlanValidationError")
        except PlanValidationError as exc:
            assert "implicit executor" in str(exc)


def test_stage_unbound_role_fails():
    paths = fixture_paths()
    sources = load_sources(
        scenario_path=paths["scenario"],
        roles_path=paths["roles"],
        executors_path=paths["executors"],
        bindings_path=paths["bindings"],
    )
    sources = copy.deepcopy(sources)
    sources["scenario"]["stages"][0]["actors"] = ["product_analyst", "architect"]
    try:
        compile_meeting_plan(
            sources,
            meeting_id=FIXED_MEETING_ID,
            topic=FIXED_TOPIC,
            generated_at=FIXED_GENERATED_AT,
        )
        raise AssertionError("expected PlanValidationError")
    except PlanValidationError as exc:
        assert "unbound role" in str(exc)


def test_duplicate_yaml_binding_key_fails():
    import tempfile

    dup = Path(tempfile.mkdtemp()) / "dup-bindings.yaml"
    dup.write_text("bindings:\n  architect: claude\n  architect: codex\n", encoding="utf-8")
    try:
        load_sources(
            scenario_path=SCENARIO,
            roles_path=FIXTURES / "roles.yaml",
            executors_path=FIXTURES / "executors.yaml",
            bindings_path=dup,
        )
        raise AssertionError("expected PlanValidationError")
    except PlanValidationError as exc:
        assert "duplicate key" in str(exc)


def test_owner_gate_stage_preserved():
    plan = compile_project_plan()
    gate = next(s for s in plan["stages"] if s["stage_id"] == "owner_gate")
    assert gate["owner_gate"] is True
    assert gate["actor_role_ids"] == []


def test_unused_binding_for_optional_role_fails():
    paths = fixture_paths()
    sources = load_sources(
        scenario_path=paths["scenario"],
        roles_path=paths["roles"],
        executors_path=paths["executors"],
        bindings_path=paths["bindings"],
    )
    sources = copy.deepcopy(sources)
    sources["bindings"]["security_reviewer"] = "claude"
    try:
        compile_meeting_plan(
            sources,
            meeting_id=FIXED_MEETING_ID,
            topic=FIXED_TOPIC,
            generated_at=FIXED_GENERATED_AT,
        )
        raise AssertionError("expected PlanValidationError")
    except PlanValidationError as exc:
        assert "unused binding" in str(exc)


def test_invalid_yaml_fails():
    import tempfile

    tmp_path = Path(tempfile.mkdtemp())
    bad = tmp_path / "bad.yaml"
    bad.write_text(":\n- [\n", encoding="utf-8")
    try:
        load_sources(
            scenario_path=bad,
            roles_path=FIXTURES / "roles.yaml",
            executors_path=FIXTURES / "executors.yaml",
            bindings_path=FIXTURES / "project-bindings.yaml",
        )
        raise AssertionError("expected PlanValidationError")
    except PlanValidationError as exc:
        assert "invalid YAML" in str(exc)


def test_non_utf8_fails():
    import tempfile

    tmp_path = Path(tempfile.mkdtemp())
    bad = tmp_path / "bad.yaml"
    bad.write_bytes(b"\xff\xfe")
    try:
        load_sources(
            scenario_path=bad,
            roles_path=FIXTURES / "roles.yaml",
            executors_path=FIXTURES / "executors.yaml",
            bindings_path=FIXTURES / "project-bindings.yaml",
        )
        raise AssertionError("expected PlanValidationError")
    except PlanValidationError as exc:
        assert "UTF-8" in str(exc)


def test_scenario_file_has_no_model_names():
    text = SCENARIO.read_text(encoding="utf-8").lower()
    for token in ("claude", "grok", "codex", "openai", "anthropic"):
        assert token not in text