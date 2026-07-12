"""Meeting plan compile demo — missionos.plan without importing council."""

from __future__ import annotations

from pathlib import Path

from missionos.plan.compiler import compile_meeting_plan
from missionos.plan.loader import load_sources

_FIXED_MEETING_ID = "meet-20260710-120000"
_FIXED_TOPIC = "Platform smoke plan"
_FIXED_GENERATED_AT = "2026-07-10T12:00:00Z"


def compile_smoke_plan_summary(repo_root: Path) -> dict[str, str | int]:
    root = Path(repo_root)
    fixtures = root / "tests" / "fixtures" / "plan"
    scenario = root / "apps" / "research_council" / "scenarios" / "project-development.yaml"
    sources = load_sources(
        scenario_path=scenario,
        roles_path=fixtures / "roles.yaml",
        executors_path=fixtures / "executors.yaml",
        bindings_path=fixtures / "project-bindings.yaml",
    )
    plan = compile_meeting_plan(
        sources,
        meeting_id=_FIXED_MEETING_ID,
        topic=_FIXED_TOPIC,
        generated_at=_FIXED_GENERATED_AT,
    )
    return {
        "schema_version": str(plan.get("schema_version", "")),
        "meeting_id": str(plan.get("meeting_id", "")),
        "participants": len(plan.get("participants", [])),
    }