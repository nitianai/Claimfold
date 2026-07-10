"""Read-only loader and snapshot immutability tests."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from types import MappingProxyType

import council.plan as plan_pkg
from council.plan import atomic_write_plan, load_meeting_plan
from council.plan.models import MeetingPlanSnapshot
from council.plan.validators import PlanValidationError
from plan_test_helpers import compile_project_plan


def test_public_all_excludes_runtime_plan():
    assert "RuntimePlan" not in plan_pkg.__all__
    assert "MeetingPlanSnapshot" in plan_pkg.__all__


def test_meeting_plan_snapshot_is_typed_read_only_view():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "meeting_plan.json"
        atomic_write_plan(path, compile_project_plan())
        snapshot = load_meeting_plan(path)
        assert isinstance(snapshot, (dict, MappingProxyType))
        assert snapshot["schema_version"] == "1.0"
        for forbidden_export in ("RuntimePlan", "PlanManager", "PlanStore", "PlanService"):
            assert forbidden_export not in plan_pkg.__all__


def test_load_meeting_plan_roundtrip():
    plan = compile_project_plan()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "meeting_plan.json"
        atomic_write_plan(path, plan)
        snapshot = load_meeting_plan(path)
        assert snapshot["meeting_id"] == plan["meeting_id"]
        assert snapshot["participants"][0]["role_id"] == plan["participants"][0]["role_id"]


def test_reader_does_not_modify_file():
    plan = compile_project_plan()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "meeting_plan.json"
        atomic_write_plan(path, plan)
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        load_meeting_plan(path)
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        assert before == after


def test_existing_plan_write_refused():
    plan = compile_project_plan()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "meeting_plan.json"
        atomic_write_plan(path, plan)
        try:
            atomic_write_plan(path, plan)
            raise AssertionError("expected failure")
        except PlanValidationError as exc:
            assert "overwrite" in str(exc)


def test_write_uses_exclusive_create():
    import threading

    plan = compile_project_plan()
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "meeting_plan.json"
        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def writer():
            try:
                barrier.wait()
                atomic_write_plan(target, plan)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(errors) == 1
        assert "overwrite" in str(errors[0])
        assert target.is_file()


def test_load_meeting_plan_returns_immutable_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "meeting_plan.json"
        atomic_write_plan(path, compile_project_plan())
        snapshot = load_meeting_plan(path)
        try:
            snapshot["topic"] = "mutated"  # type: ignore[index]
            raise AssertionError("expected immutability failure")
        except TypeError:
            pass


def test_unknown_version_on_read_fail_closed():
    plan = compile_project_plan()
    plan["schema_version"] = "99.0"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "meeting_plan.json"
        path.write_text(__import__("json").dumps(plan, indent=2) + "\n", encoding="utf-8")
        try:
            load_meeting_plan(path)
            raise AssertionError("expected failure")
        except PlanValidationError as exc:
            assert "unsupported schema_version" in str(exc)