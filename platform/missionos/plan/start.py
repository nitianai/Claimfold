"""Compile meeting plan during ``council start --scenario``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from missionos.plan.compiler import compile_meeting_plan
from missionos.plan.loader import load_sources
from missionos.plan.paths import PlanLayout, resolve_plan_inputs
from missionos.plan.validators import PlanValidationError


def build_meeting_plan(
    *,
    scenario: str,
    meeting_id: str,
    topic: str,
    generated_at: str,
    layout: PlanLayout,
    bindings_path: str | Path | None = None,
    roles_path: str | Path | None = None,
    executors_path: str | Path | None = None,
    cli_bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Load sources and compile a validated meeting plan dict."""
    inputs = resolve_plan_inputs(
        scenario=scenario,
        layout=layout,
        bindings_path=bindings_path,
        roles_path=roles_path,
        executors_path=executors_path,
    )
    sources = load_sources(**inputs)
    return compile_meeting_plan(
        sources,
        meeting_id=meeting_id,
        topic=topic,
        generated_at=generated_at,
        cli_bindings=cli_bindings or None,
    )


def first_stage_binding(plan: dict[str, Any]) -> tuple[str, str]:
    """Return (role_id, executor_id) for the first non-owner stage actor."""
    participants_by_role = {p["role_id"]: p["executor_id"] for p in plan["participants"]}
    for stage in plan.get("stages", []):
        if stage.get("owner_gate"):
            continue
        for role_id in stage.get("actor_role_ids", []):
            executor_id = participants_by_role.get(role_id)
            if executor_id:
                return role_id, executor_id
    first = plan["participants"][0]
    return first["role_id"], first["executor_id"]


def first_stage_executor_id(plan: dict[str, Any]) -> str:
    """Pick executor for the first non-owner stage actor."""
    return first_stage_binding(plan)[1]


__all__ = ["PlanValidationError", "build_meeting_plan", "first_stage_executor_id"]