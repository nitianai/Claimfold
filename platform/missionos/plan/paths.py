"""Resolve scenario / roles / executors / bindings paths for meeting start."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from missionos.plan.validators import PlanValidationError


@dataclass(frozen=True)
class PlanLayout:
    """Injected config paths — no App config imports."""

    root: Path
    scenarios_dir: Path
    roles_file: Path
    executors_file: Path
    bindings_dir: Path


def normalize_scenario_slug(scenario: str) -> str:
    text = scenario.strip()
    if not text:
        raise PlanValidationError("scenario id cannot be empty")
    return text.replace("_", "-")


def resolve_scenario_path(scenario: str, *, layout: PlanLayout) -> Path:
    slug = normalize_scenario_slug(scenario)
    path = layout.scenarios_dir / f"{slug}.yaml"
    if not path.is_file():
        raise PlanValidationError(f"scenario not found: {slug} (expected {path})")
    return path


def _resolve_optional_path(
    raw: str | Path | None,
    *,
    layout: PlanLayout,
    label: str,
) -> Path | None:
    if raw is None:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = layout.root / path
    if not path.is_file():
        raise PlanValidationError(f"{label} not found: {path}")
    return path


def resolve_bindings_path(
    scenario: str,
    explicit: str | Path | None = None,
    *,
    layout: PlanLayout,
) -> Path:
    if explicit is not None:
        return _resolve_optional_path(explicit, layout=layout, label="bindings file")
    slug = normalize_scenario_slug(scenario)
    default = layout.bindings_dir / f"{slug}.yaml"
    if default.is_file():
        return default
    raise PlanValidationError(
        f"bindings required for scenario {slug!r}: pass --bindings or add {default}"
    )


def resolve_plan_inputs(
    *,
    scenario: str,
    layout: PlanLayout,
    bindings_path: str | Path | None = None,
    roles_path: str | Path | None = None,
    executors_path: str | Path | None = None,
) -> dict[str, Path]:
    """Return load_sources keyword paths."""
    roles = (
        _resolve_optional_path(roles_path, layout=layout, label="roles file")
        if roles_path
        else layout.roles_file
    )
    executors = (
        _resolve_optional_path(executors_path, layout=layout, label="executors file")
        if executors_path
        else layout.executors_file
    )
    if not roles.is_file():
        raise PlanValidationError(f"roles file not found: {roles}")
    if not executors.is_file():
        raise PlanValidationError(f"executors file not found: {executors}")
    return {
        "scenario_path": resolve_scenario_path(scenario, layout=layout),
        "roles_path": roles,
        "executors_path": executors,
        "bindings_path": resolve_bindings_path(scenario, bindings_path, layout=layout),
    }