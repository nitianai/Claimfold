"""Source document loading (I/O layer)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from missionos.plan.validators import PlanValidationError


def _construct_mapping_no_duplicates(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise PlanValidationError(f"duplicate key in YAML: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


def _load_yaml(path: Path, *, label: str) -> Any:
    if not path.is_file():
        raise PlanValidationError(f"{label} not found: {path}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PlanValidationError(f"cannot read {label}: {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanValidationError(f"{label} must be UTF-8: {path}") from exc
    try:
        data = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise PlanValidationError(f"invalid YAML in {label}: {path}: {exc}") from exc
    if data is None:
        raise PlanValidationError(f"{label} is empty: {path}")
    if not isinstance(data, dict):
        raise PlanValidationError(f"{label} must be a mapping: {path}")
    return data


def _bindings_mapping(data: dict[str, Any], *, path: Path) -> dict[str, str]:
    bindings = data.get("bindings")
    if bindings is None:
        raise PlanValidationError(f"bindings file missing 'bindings' key: {path}")
    if not isinstance(bindings, dict):
        raise PlanValidationError(f"'bindings' must be a mapping: {path}")
    out: dict[str, str] = {}
    for role_id, executor_id in bindings.items():
        if not isinstance(role_id, str) or not role_id.strip():
            raise PlanValidationError(f"invalid role key in bindings: {role_id!r} ({path})")
        if not isinstance(executor_id, str) or not executor_id.strip():
            raise PlanValidationError(
                f"invalid executor for role {role_id!r} in bindings: {executor_id!r} ({path})"
            )
        if role_id in out:
            raise PlanValidationError(f"duplicate role binding in file: {role_id} ({path})")
        out[role_id] = executor_id.strip()
    return out


def _roles_index(data: dict[str, Any], *, path: Path) -> dict[str, dict[str, Any]]:
    roles = data.get("roles")
    if roles is None:
        raise PlanValidationError(f"roles file missing 'roles' key: {path}")
    if not isinstance(roles, dict) or not roles:
        raise PlanValidationError(f"'roles' must be a non-empty mapping: {path}")
    for role_id, role in roles.items():
        if not isinstance(role, dict):
            raise PlanValidationError(f"role {role_id!r} must be a mapping: {path}")
        declared = role.get("role_id", role_id)
        if declared != role_id:
            raise PlanValidationError(
                f"role_id mismatch: key {role_id!r} vs role.role_id {declared!r} ({path})"
            )
    return roles


def _executors_index(data: dict[str, Any], *, path: Path) -> dict[str, dict[str, Any]]:
    executors = data.get("executors")
    if executors is None:
        raise PlanValidationError(f"executors file missing 'executors' key: {path}")
    if not isinstance(executors, dict) or not executors:
        raise PlanValidationError(f"'executors' must be a non-empty mapping: {path}")
    for executor_id, executor in executors.items():
        if not isinstance(executor, dict):
            raise PlanValidationError(f"executor {executor_id!r} must be a mapping: {path}")
    return executors


def load_sources(
    *,
    scenario_path: Path,
    roles_path: Path,
    executors_path: Path,
    bindings_path: Path,
) -> dict[str, Any]:
    """Load scenario, roles, executors, and bindings from disk."""
    scenario = _load_yaml(scenario_path, label="scenario")
    roles_data = _load_yaml(roles_path, label="roles")
    executors_data = _load_yaml(executors_path, label="executors")
    bindings_data = _load_yaml(bindings_path, label="bindings")

    return {
        "scenario": scenario,
        "roles": _roles_index(roles_data, path=roles_path),
        "executors": _executors_index(executors_data, path=executors_path),
        "bindings": _bindings_mapping(bindings_data, path=bindings_path),
        "_paths": {
            "scenario": str(scenario_path.resolve()),
            "roles": str(roles_path.resolve()),
            "executors": str(executors_path.resolve()),
            "bindings": str(bindings_path.resolve()),
        },
    }