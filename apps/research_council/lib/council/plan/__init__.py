"""Meeting plan compile/read pipeline — re-exports missionos.plan + App runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from missionos.plan.cli_bindings import parse_cli_bindings
from missionos.plan.compiler import compile_meeting_plan
from missionos.plan.loader import load_sources
from missionos.plan.models import (
    CURRENT_SCHEMA_VERSION,
    MeetingPlanSnapshot,
    SUPPORTED_SCHEMA_VERSIONS,
)
from missionos.plan.reader import load_meeting_plan
from missionos.plan.start import first_stage_binding, first_stage_executor_id
from missionos.plan.validators import PlanValidationError, validate_plan
from missionos.plan.writer import atomic_write_plan, canonical_json_bytes
from missionos.plan.start import build_meeting_plan as _build_meeting_plan

from council.plan.paths import (
    default_plan_layout,
    resolve_plan_inputs,
    resolve_scenario_path,
)
from council.adapters.plan_runtime import (
    advance_plan_speaker,
    build_plan_actor_queue,
    load_state_plan,
    plan_guest_roster,
)


def build_meeting_plan(
    *,
    scenario: str,
    meeting_id: str,
    topic: str,
    generated_at: str,
    bindings_path: str | Path | None = None,
    roles_path: str | Path | None = None,
    executors_path: str | Path | None = None,
    cli_bindings: dict[str, str] | None = None,
    layout: Any | None = None,
) -> dict[str, Any]:
    return _build_meeting_plan(
        scenario=scenario,
        meeting_id=meeting_id,
        topic=topic,
        generated_at=generated_at,
        layout=layout or default_plan_layout(),
        bindings_path=bindings_path,
        roles_path=roles_path,
        executors_path=executors_path,
        cli_bindings=cli_bindings,
    )


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "MeetingPlanSnapshot",
    "PlanValidationError",
    "atomic_write_plan",
    "advance_plan_speaker",
    "build_meeting_plan",
    "build_plan_actor_queue",
    "canonical_json_bytes",
    "compile_meeting_plan",
    "first_stage_binding",
    "first_stage_executor_id",
    "load_meeting_plan",
    "load_state_plan",
    "plan_guest_roster",
    "load_sources",
    "parse_cli_bindings",
    "resolve_plan_inputs",
    "resolve_scenario_path",
    "validate_plan",
]