"""Schema and semantic validation for meeting plans."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from council.plan.models import (
    CURRENT_SCHEMA_VERSION,
    EXECUTOR_SNAPSHOT_ALLOWED_KEYS,
    FORBIDDEN_SECRET_KEYS,
    ROLE_SNAPSHOT_ALLOWED_KEYS,
    SUPPORTED_SCHEMA_VERSIONS,
)

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "meeting_plan.schema.json"

_SECRET_REF_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SECRET_VALUE_PATTERNS = [
    re.compile(r"^sk-[A-Za-z0-9]{10,}$"),
    re.compile(r"^Bearer\s+\S+", re.I),
    re.compile(r"^glpat-[A-Za-z0-9\-_]{10,}$"),
]
_AUTH_ARG_PREFIXES = ("--api-key", "--api_key", "--token", "--password", "--secret")


class PlanValidationError(Exception):
    """Validation failure with a human-readable message."""

    def __init__(self, message: str, *, path: str = "") -> None:
        self.path = path
        full = f"{path}: {message}" if path else message
        super().__init__(full)


def _sha256_hex(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _merge_bindings(
    file_bindings: dict[str, str],
    cli_bindings: dict[str, str] | None,
) -> tuple[dict[str, str], str]:
    merged = dict(file_bindings)
    if not cli_bindings:
        return merged, "file"
    for role_id, executor_id in cli_bindings.items():
        if not isinstance(role_id, str) or not role_id.strip():
            raise PlanValidationError(f"invalid CLI bind role: {role_id!r}")
        if not isinstance(executor_id, str) or not executor_id.strip():
            raise PlanValidationError(f"invalid CLI bind executor for {role_id!r}: {executor_id!r}")
        merged[role_id] = executor_id.strip()
    return merged, "cli+file"


def _is_forbidden_key(key: str) -> bool:
    normalized = str(key).lower().replace("-", "_")
    if normalized in FORBIDDEN_SECRET_KEYS:
        return True
    return any(part in normalized for part in ("api_key", "client_secret", "access_token", "private_key"))


def _validate_secret_ref_name(ref: str, *, path: str) -> None:
    if not _SECRET_REF_NAME_RE.match(ref):
        raise PlanValidationError(
            f"secret_refs must be env-style names (e.g. ANTHROPIC_API_KEY): {ref!r}",
            path=path,
        )
    for pattern in _SECRET_VALUE_PATTERNS:
        if pattern.search(ref):
            raise PlanValidationError(f"secret_refs must be names only, not values: {ref!r}", path=path)


def _validate_command_template(template: Any, *, path: str) -> None:
    if template is None:
        return
    if not isinstance(template, list) or not all(isinstance(item, str) for item in template):
        raise PlanValidationError("command_template must be a list of strings", path=path)
    prev_was_auth_flag = False
    for idx, token in enumerate(template):
        if prev_was_auth_flag:
            if token.startswith("{") and token.endswith("}"):
                prev_was_auth_flag = False
                continue
            raise PlanValidationError(
                f"command_template auth flag must be followed by placeholder, not literal: {token!r}",
                path=path,
            )
        lower = token.lower()
        if lower in _AUTH_ARG_PREFIXES:
            prev_was_auth_flag = True
        for pattern in _SECRET_VALUE_PATTERNS:
            if pattern.search(token):
                raise PlanValidationError("command_template contains secret-like literal", path=path)
        if _is_forbidden_key(token):
            raise PlanValidationError(f"command_template contains forbidden token: {token!r}", path=path)
    if prev_was_auth_flag:
        raise PlanValidationError("command_template auth flag missing value placeholder", path=path)


def _enforce_allowlist(mapping: dict[str, Any], allowed: frozenset[str], *, label: str, path: str) -> None:
    extra = set(mapping) - set(allowed)
    if extra:
        raise PlanValidationError(f"{label} contains disallowed fields: {sorted(extra)}", path=path)


def _walk_for_secrets(obj: Any, path: str = "", *, in_command_template: bool = False) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = str(key).lower().replace("-", "_")
            if _is_forbidden_key(str(key)):
                raise PlanValidationError(f"forbidden secret key {key!r}", path=path or "$")
            child = f"{path}.{key}" if path else str(key)
            if key_lower == "secret_refs":
                if not isinstance(value, list):
                    raise PlanValidationError("secret_refs must be a list", path=child)
                for ref in value:
                    if not isinstance(ref, str) or not ref.strip():
                        raise PlanValidationError("secret_refs entries must be non-empty strings", path=child)
                    _validate_secret_ref_name(ref.strip(), path=child)
                continue
            if key_lower == "command_template":
                _validate_command_template(value, path=child)
                continue
            _walk_for_secrets(value, child)
    elif isinstance(obj, list):
        if in_command_template:
            _validate_command_template(obj, path=path)
            return
        for idx, item in enumerate(obj):
            _walk_for_secrets(item, f"{path}[{idx}]")
    elif isinstance(obj, str):
        for pattern in _SECRET_VALUE_PATTERNS:
            if pattern.search(obj):
                raise PlanValidationError("value resembles a secret", path=path or "$")


def validate_schema_version(version: Any) -> str:
    if version is None:
        raise PlanValidationError("missing schema_version")
    if not isinstance(version, str) or not version.strip():
        raise PlanValidationError(f"invalid schema_version: {version!r}")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise PlanValidationError(f"unsupported schema_version: {version!r}")
    return version


def _json_schema_validator() -> Draft202012Validator:
    schema = load_schema_document()
    return Draft202012Validator(schema)


def validate_json_schema(plan: dict[str, Any]) -> None:
    """Validate plan against meeting_plan.schema.json (Draft 2020-12)."""
    validator = _json_schema_validator()
    errors = sorted(validator.iter_errors(plan), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    err = errors[0]
    path = ".".join(str(p) for p in err.absolute_path) or "$"
    raise PlanValidationError(err.message, path=path)


def validate_schema_structure(plan: dict[str, Any]) -> None:
    """Structural validation via JSON Schema document."""
    validate_json_schema(plan)


def validate_semantics(plan: dict[str, Any]) -> None:
    """Cross-field semantic rules beyond JSON Schema."""
    participants = plan["participants"]
    role_ids: list[str] = []
    participant_ids: list[str] = []
    bindings_seen: dict[str, str] = {}
    participant_role_set = {p["role_id"] for p in participants}

    for participant in participants:
        role_id = participant["role_id"]
        participant_id = participant["participant_id"]
        executor_id = participant["executor_id"]

        if role_id in role_ids:
            raise PlanValidationError(f"duplicate role_id in participants: {role_id}")
        role_ids.append(role_id)

        if participant_id in participant_ids:
            raise PlanValidationError(f"duplicate participant_id: {participant_id}")
        participant_ids.append(participant_id)

        if role_id in bindings_seen and bindings_seen[role_id] != executor_id:
            raise PlanValidationError(f"conflicting executor for role {role_id}")
        bindings_seen[role_id] = executor_id

        role_snap = participant["role_snapshot"]
        if role_snap.get("role_id") != role_id:
            raise PlanValidationError(f"role_snapshot.role_id mismatch for {role_id}")
        _enforce_allowlist(role_snap, ROLE_SNAPSHOT_ALLOWED_KEYS, label="role_snapshot", path=participant_id)

        exec_snap = participant["executor_snapshot"]
        if exec_snap.get("executor_id") != executor_id:
            raise PlanValidationError(f"executor_snapshot.executor_id mismatch for {executor_id}")
        if exec_snap.get("enabled") is False:
            raise PlanValidationError(f"disabled executor in plan: {executor_id}")
        _enforce_allowlist(
            exec_snap,
            EXECUTOR_SNAPSHOT_ALLOWED_KEYS,
            label="executor_snapshot",
            path=participant_id,
        )
        _walk_for_secrets(exec_snap, f"participants.{participant_id}.executor_snapshot")

    for stage in plan.get("stages", []):
        if stage.get("owner_gate"):
            if stage.get("actor_role_ids"):
                raise PlanValidationError(
                    f"owner_gate stage {stage.get('stage_id')!r} must not list council actor_role_ids"
                )
            continue
        for role_id in stage.get("actor_role_ids", []):
            if role_id not in participant_role_set:
                raise PlanValidationError(
                    f"stage {stage.get('stage_id')!r} references unbound role {role_id!r}"
                )

    policy = plan.get("decision_policy") or {}
    if policy.get("council_can_decide") is True:
        raise PlanValidationError("decision_policy.council_can_decide must not be true in PR1 plans")


def validate_plan(plan: dict[str, Any]) -> None:
    """Full validation: JSON Schema shape first, then semantics."""
    if not isinstance(plan, dict):
        raise PlanValidationError("plan must be a mapping")
    validate_schema_version(plan.get("schema_version"))
    validate_json_schema(plan)
    validate_semantics(plan)


def schema_document_path() -> Path:
    return _SCHEMA_PATH


def load_schema_document() -> dict[str, Any]:
    if not _SCHEMA_PATH.is_file():
        raise PlanValidationError(f"schema file missing: {_SCHEMA_PATH}")
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))