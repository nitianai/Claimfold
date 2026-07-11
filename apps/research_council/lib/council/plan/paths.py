"""App shim: inject council.config paths into missionos.plan.paths."""

from __future__ import annotations

from pathlib import Path

from council.config import BINDINGS_DIR, EXECUTORS_FILE, ROLES_FILE, ROOT, SCENARIOS_DIR
from missionos.plan.paths import (
    PlanLayout,
    normalize_scenario_slug,
    resolve_bindings_path as _resolve_bindings_path,
    resolve_plan_inputs as _resolve_plan_inputs,
    resolve_scenario_path as _resolve_scenario_path,
)

__all__ = [
    "PlanLayout",
    "default_plan_layout",
    "normalize_scenario_slug",
    "resolve_bindings_path",
    "resolve_plan_inputs",
    "resolve_scenario_path",
]


def default_plan_layout() -> PlanLayout:
    return PlanLayout(
        root=ROOT,
        scenarios_dir=SCENARIOS_DIR,
        roles_file=ROLES_FILE,
        executors_file=EXECUTORS_FILE,
        bindings_dir=BINDINGS_DIR,
    )


def resolve_scenario_path(scenario: str) -> Path:
    return _resolve_scenario_path(scenario, layout=default_plan_layout())


def resolve_bindings_path(scenario: str, explicit: str | Path | None = None) -> Path:
    return _resolve_bindings_path(scenario, explicit=explicit, layout=default_plan_layout())


def resolve_plan_inputs(
    *,
    scenario: str,
    bindings_path: str | Path | None = None,
    roles_path: str | Path | None = None,
    executors_path: str | Path | None = None,
) -> dict[str, Path]:
    return _resolve_plan_inputs(
        scenario=scenario,
        layout=default_plan_layout(),
        bindings_path=bindings_path,
        roles_path=roles_path,
        executors_path=executors_path,
    )