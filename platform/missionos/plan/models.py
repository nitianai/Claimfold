"""Public read types and compile-time constants for meeting plans."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

CURRENT_SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({CURRENT_SCHEMA_VERSION})

# Executor snapshot — allowed non-sensitive fields (Owner Decision §1).
EXECUTOR_SNAPSHOT_ALLOWED_KEYS = frozenset(
    {
        "executor_id",
        "type",
        "adapter",
        "model",
        "timeout_seconds",
        "command_template",
        "capabilities",
        "enabled",
        "secret_refs",
    }
)

# Keys forbidden anywhere in executor snapshots (case-insensitive match).
FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "token",
        "api_key",
        "apikey",
        "password",
        "credential",
        "cookie",
        "session",
        "private_key",
        "secret",
        "auth",
        "authorization",
        "bearer",
        "access_token",
        "client_secret",
    }
)

# Role snapshot — minimal audit fields.
ROLE_SNAPSHOT_ALLOWED_KEYS = frozenset(
    {
        "role_id",
        "name",
        "purpose",
        "authority",
    }
)


class ExecutorSnapshot(TypedDict):
    executor_id: str
    type: str
    adapter: NotRequired[str]
    model: NotRequired[str]
    timeout_seconds: NotRequired[int]
    command_template: NotRequired[list[str]]
    capabilities: NotRequired[list[str]]
    enabled: bool
    secret_refs: NotRequired[list[str]]


class RoleSnapshot(TypedDict):
    role_id: str
    name: str
    purpose: str
    authority: NotRequired[dict[str, Any]]


class ParticipantSnapshot(TypedDict):
    participant_id: str
    role_id: str
    role_snapshot: RoleSnapshot
    executor_id: str
    executor_snapshot: ExecutorSnapshot


class ScenarioRef(TypedDict):
    id: str
    version: str
    source_sha256: str


class StageSnapshot(TypedDict):
    stage_id: str
    name: str
    actor_role_ids: list[str]
    owner_gate: bool


class ProvenanceSnapshot(TypedDict):
    bindings_sha256: str
    bindings_source: str
    generated_at: str


class MeetingPlanSnapshot(TypedDict):
    """Read-only view of a frozen meeting_plan.json artifact."""

    schema_version: str
    meeting_id: str
    topic: str
    scenario: ScenarioRef
    participants: list[ParticipantSnapshot]
    stages: list[StageSnapshot]
    decision_policy: dict[str, Any]
    provenance: ProvenanceSnapshot


class SourceDocuments(TypedDict):
    scenario: dict[str, Any]
    roles: dict[str, Any]
    executors: dict[str, Any]
    bindings: dict[str, str]