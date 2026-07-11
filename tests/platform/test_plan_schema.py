"""Schema document and structural validation tests."""

from __future__ import annotations

from council.plan import CURRENT_SCHEMA_VERSION
from missionos.plan.validators import (
    PlanValidationError,
    load_schema_document,
    schema_document_path,
    validate_plan,
    validate_schema_version,
)
from plan_test_helpers import compile_project_plan


def test_schema_file_exists():
    path = schema_document_path()
    assert path.is_file()
    doc = load_schema_document()
    assert doc["properties"]["schema_version"]["enum"] == [CURRENT_SCHEMA_VERSION]


def test_malformed_plan_raises_validation_error_not_keyerror():
    try:
        validate_plan({"schema_version": "1.0"})
        raise AssertionError("expected failure")
    except PlanValidationError:
        pass
    except KeyError as exc:
        raise AssertionError(f"KeyError instead of PlanValidationError: {exc}") from exc


def test_missing_schema_version_fails():
    plan = compile_project_plan()
    del plan["schema_version"]
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "schema_version" in str(exc)


def test_unknown_schema_version_fail_closed():
    try:
        validate_schema_version("9.9")
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "unsupported" in str(exc)


def test_schema_valid_but_semantics_invalid():
    plan = compile_project_plan()
    plan["participants"].append(plan["participants"][0])
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "duplicate" in str(exc)


def test_json_schema_rejects_extra_top_level_field():
    plan = compile_project_plan()
    plan["extra_field"] = "not-allowed"
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "Additional properties" in str(exc) or "not allowed" in str(exc).lower()


def test_json_schema_rejects_invalid_sha256():
    plan = compile_project_plan()
    plan["scenario"]["source_sha256"] = "not-a-hash"
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "source_sha256" in str(exc) or "pattern" in str(exc).lower()