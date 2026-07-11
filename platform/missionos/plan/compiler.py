"""Pure meeting plan compiler — no I/O, no side effects."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from missionos.plan.models import (
    CURRENT_SCHEMA_VERSION,
    EXECUTOR_SNAPSHOT_ALLOWED_KEYS,
    ROLE_SNAPSHOT_ALLOWED_KEYS,
)
from missionos.plan.validators import PlanValidationError, _merge_bindings, _sha256_hex


def _role_snapshot(role: dict[str, Any], role_id: str) -> dict[str, Any]:
    snap: dict[str, Any] = {"role_id": role_id}
    for key in ROLE_SNAPSHOT_ALLOWED_KEYS:
        if key == "role_id":
            continue
        if key in role:
            snap[key] = deepcopy(role[key])
    if "name" not in snap:
        snap["name"] = role_id
    if "purpose" not in snap:
        raise PlanValidationError(f"role {role_id!r} missing required field 'purpose'")
    return snap


def _executor_snapshot(executor_id: str, executor: dict[str, Any]) -> dict[str, Any]:
    snap: dict[str, Any] = {"executor_id": executor_id}
    for key in EXECUTOR_SNAPSHOT_ALLOWED_KEYS:
        if key == "executor_id":
            continue
        if key in executor:
            snap[key] = deepcopy(executor[key])
    if "type" not in snap:
        raise PlanValidationError(f"executor {executor_id!r} missing required field 'type'")
    snap["enabled"] = bool(executor.get("enabled", True))
    return snap


def _stage_snapshots(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    stages = scenario.get("stages") or []
    if not isinstance(stages, list):
        raise PlanValidationError("scenario.stages must be a list")
    out: list[dict[str, Any]] = []
    for idx, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise PlanValidationError(f"stage[{idx}] must be a mapping")
        stage_id = stage.get("id")
        if not isinstance(stage_id, str) or not stage_id.strip():
            raise PlanValidationError(f"stage[{idx}] missing 'id'")
        actors = stage.get("actors") or []
        if not isinstance(actors, list):
            raise PlanValidationError(f"stage {stage_id!r} actors must be a list")

        owner_gate = False
        actor_role_ids: list[str] = []
        for actor in actors:
            if actor == "owner":
                owner_gate = True
            elif isinstance(actor, str) and actor.strip():
                actor_role_ids.append(actor.strip())
            else:
                raise PlanValidationError(f"stage {stage_id!r} has invalid actor entry: {actor!r}")

        if owner_gate and actor_role_ids:
            raise PlanValidationError(
                f"stage {stage_id!r} cannot mix owner gate with council actor_role_ids"
            )

        out.append(
            {
                "stage_id": stage_id,
                "name": stage.get("name", stage_id),
                "actor_role_ids": actor_role_ids,
                "owner_gate": owner_gate,
            }
        )
    return out


def _validate_stage_closure(stages: list[dict[str, Any]], participant_roles: set[str]) -> None:
    for stage in stages:
        if stage.get("owner_gate"):
            continue
        for role_id in stage["actor_role_ids"]:
            if role_id not in participant_roles:
                raise PlanValidationError(
                    f"stage {stage['stage_id']!r} references unbound role {role_id!r}"
                )


def compile_meeting_plan(
    source_docs: dict[str, Any],
    *,
    meeting_id: str,
    topic: str,
    generated_at: str,
    cli_bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compile source documents into a meeting plan dict (not yet written)."""
    scenario = source_docs["scenario"]
    roles: dict[str, Any] = source_docs["roles"]
    executors: dict[str, Any] = source_docs["executors"]
    file_bindings: dict[str, str] = source_docs["bindings"]

    scenario_id = scenario.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise PlanValidationError("scenario missing required field 'scenario_id'")

    forbidden_keys = ("default_executor", "executors", "executor", "implicit_executor")
    for key in forbidden_keys:
        if key in scenario:
            raise PlanValidationError(f"scenario must not specify implicit executor field '{key}'")

    required_roles = scenario.get("required_roles") or []
    if not isinstance(required_roles, list) or not required_roles:
        raise PlanValidationError("scenario.required_roles must be a non-empty list")

    merged_bindings, bindings_source = _merge_bindings(file_bindings, cli_bindings)

    participants: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    seen_participants: set[str] = set()

    for role_id in required_roles:
        if not isinstance(role_id, str) or not role_id.strip():
            raise PlanValidationError(f"invalid required_role entry: {role_id!r}")
        if role_id in seen_roles:
            raise PlanValidationError(f"duplicate required_role: {role_id}")
        seen_roles.add(role_id)

        if role_id not in roles:
            raise PlanValidationError(f"role not found: {role_id}")

        executor_id = merged_bindings.get(role_id)
        if not executor_id:
            raise PlanValidationError(f"required role {role_id!r} has no executor binding")

        if executor_id not in executors:
            raise PlanValidationError(
                f"binding references unknown executor {executor_id!r} for role {role_id!r}"
            )

        executor = executors[executor_id]
        if not executor.get("enabled", True):
            raise PlanValidationError(f"executor {executor_id!r} is disabled")

        participant_id = f"{role_id}-01"
        if participant_id in seen_participants:
            raise PlanValidationError(f"duplicate participant_id: {participant_id}")
        seen_participants.add(participant_id)

        participants.append(
            {
                "participant_id": participant_id,
                "role_id": role_id,
                "role_snapshot": _role_snapshot(roles[role_id], role_id),
                "executor_id": executor_id,
                "executor_snapshot": _executor_snapshot(executor_id, executor),
            }
        )

    required_set = set(required_roles)
    for bound_role, bound_executor in merged_bindings.items():
        if bound_role not in roles:
            raise PlanValidationError(f"bindings reference unknown role: {bound_role}")
        if bound_executor not in executors:
            raise PlanValidationError(
                f"bindings reference unknown executor {bound_executor!r} for role {bound_role}"
            )
        if bound_role not in required_set:
            raise PlanValidationError(f"unused binding for non-required role: {bound_role}")

    participant_roles = {p["role_id"] for p in participants}
    stages = _stage_snapshots(scenario)
    _validate_stage_closure(stages, participant_roles)

    scenario_version = str(scenario.get("version", "1.0"))
    scenario_canonical = json.dumps(scenario, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    bindings_canonical = json.dumps(merged_bindings, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    plan: dict[str, Any] = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "meeting_id": meeting_id,
        "topic": topic,
        "scenario": {
            "id": scenario_id,
            "version": scenario_version,
            "source_sha256": _sha256_hex(scenario_canonical),
        },
        "participants": participants,
        "stages": stages,
        "decision_policy": deepcopy(scenario.get("decision_policy") or {}),
        "termination": deepcopy(scenario.get("termination") or {}),
        "provenance": {
            "bindings_sha256": _sha256_hex(bindings_canonical),
            "bindings_source": bindings_source,
            "generated_at": generated_at,
        },
    }
    return plan