"""Shared helpers for meeting plan PR1 tests."""

from __future__ import annotations

from pathlib import Path

from missionos.plan.compiler import compile_meeting_plan
from missionos.plan.loader import load_sources

ROOT = Path(__file__).resolve().parent.parent.parent
APP_ROOT = ROOT / "apps" / "research_council"
FIXTURES = ROOT / "tests" / "fixtures" / "plan"
SCENARIO = APP_ROOT / "scenarios" / "project-development.yaml"

FIXED_MEETING_ID = "meet-20260710-120000"
FIXED_TOPIC = "Owner Dashboard 开发"
FIXED_GENERATED_AT = "2026-07-10T12:00:00Z"


def fixture_paths() -> dict[str, Path]:
    return {
        "scenario": SCENARIO,
        "roles": FIXTURES / "roles.yaml",
        "executors": FIXTURES / "executors.yaml",
        "bindings": FIXTURES / "project-bindings.yaml",
    }


def compile_project_plan(*, cli_bindings: dict[str, str] | None = None) -> dict:
    paths = fixture_paths()
    sources = load_sources(
        scenario_path=paths["scenario"],
        roles_path=paths["roles"],
        executors_path=paths["executors"],
        bindings_path=paths["bindings"],
    )
    return compile_meeting_plan(
        sources,
        meeting_id=FIXED_MEETING_ID,
        topic=FIXED_TOPIC,
        generated_at=FIXED_GENERATED_AT,
        cli_bindings=cli_bindings,
    )