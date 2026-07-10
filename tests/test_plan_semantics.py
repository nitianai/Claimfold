"""Semantic validation tests."""

from __future__ import annotations

import copy

from council.plan.validators import PlanValidationError, validate_plan
from plan_test_helpers import compile_project_plan


def test_secret_value_in_executor_snapshot_fails():
    plan = compile_project_plan()
    plan = copy.deepcopy(plan)
    plan["participants"][0]["executor_snapshot"]["api_key"] = "sk-abcdefghijklmnopqrstuvwxyz"
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "forbidden secret key" in str(exc).lower() or "api_key" in str(exc)


def test_secret_refs_must_be_names_not_values():
    plan = compile_project_plan()
    plan = copy.deepcopy(plan)
    plan["participants"][0]["executor_snapshot"]["secret_refs"] = ["sk-live-bad"]
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "secret_refs" in str(exc)


def test_council_can_decide_must_not_be_true():
    plan = compile_project_plan()
    plan = copy.deepcopy(plan)
    plan["decision_policy"]["council_can_decide"] = True
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "council_can_decide" in str(exc)


def test_duplicate_participant_id_fails():
    plan = compile_project_plan()
    plan = copy.deepcopy(plan)
    plan["participants"][1]["participant_id"] = plan["participants"][0]["participant_id"]
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "duplicate participant_id" in str(exc)


def test_bearer_token_in_snapshot_value_fails():
    plan = compile_project_plan()
    plan = copy.deepcopy(plan)
    plan["participants"][0]["executor_snapshot"]["note"] = "Bearer abc.def.ghi"
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "disallowed" in str(exc).lower() or "secret" in str(exc).lower()


def test_access_token_key_rejected():
    plan = compile_project_plan()
    plan = copy.deepcopy(plan)
    plan["participants"][0]["executor_snapshot"]["access_token"] = "plain-secret"
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "disallowed" in str(exc).lower() or "forbidden" in str(exc).lower()


def test_command_template_literal_secret_rejected():
    plan = compile_project_plan()
    plan = copy.deepcopy(plan)
    plan["participants"][0]["executor_snapshot"]["command_template"] = [
        "opencode",
        "--api-key",
        "plain-secret",
    ]
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "command_template" in str(exc)


def test_secret_refs_bearer_name_rejected():
    plan = compile_project_plan()
    plan = copy.deepcopy(plan)
    plan["participants"][0]["executor_snapshot"]["secret_refs"] = ["Bearer abc"]
    try:
        validate_plan(plan)
        raise AssertionError("expected failure")
    except PlanValidationError as exc:
        assert "secret_refs" in str(exc)