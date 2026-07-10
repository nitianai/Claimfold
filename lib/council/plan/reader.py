"""Read-only meeting plan loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from council.plan.models import MeetingPlanSnapshot
from council.plan.validators import PlanValidationError, validate_plan


def load_meeting_plan(path: Path) -> MeetingPlanSnapshot:
    """Load, validate, and return a read-only snapshot of meeting_plan.json."""
    if not path.is_file():
        raise PlanValidationError(f"meeting plan not found: {path}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PlanValidationError(f"cannot read plan: {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanValidationError(f"plan must be UTF-8: {path}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f"invalid JSON in plan: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanValidationError(f"plan root must be an object: {path}")
    validate_plan(data)
    return cast(MeetingPlanSnapshot, data)