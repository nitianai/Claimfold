"""Session health checks for Mission OS daemon."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from missionos.protocols import SessionStoreProtocol


@dataclass(frozen=True)
class SessionHealth:
    ok: bool
    meeting_id: str | None
    meeting_dir: Path | None
    state_mtime: float | None
    issues: tuple[str, ...]


def _safe_validate(validate_fn: Callable[[str], str] | None, meeting_id: str) -> tuple[str | None, str | None]:
    if validate_fn is None:
        return meeting_id, None
    try:
        return validate_fn(meeting_id), None
    except SystemExit as exc:
        return None, str(exc) or f"invalid meeting id: {meeting_id!r}"


def check_session_health(
    store: SessionStoreProtocol,
    *,
    validate_fn: Callable[[str], str] | None = None,
) -> SessionHealth:
    issues: list[str] = []

    if not store.pointer_path.exists():
        return SessionHealth(
            ok=False,
            meeting_id=None,
            meeting_dir=None,
            state_mtime=None,
            issues=("no active session pointer",),
        )

    meeting_id = store.read_pointer().strip()
    if not meeting_id:
        return SessionHealth(
            ok=False,
            meeting_id=None,
            meeting_dir=None,
            state_mtime=None,
            issues=("session pointer is empty",),
        )

    validated_id, validate_err = _safe_validate(validate_fn, meeting_id)
    if validate_err:
        return SessionHealth(
            ok=False,
            meeting_id=meeting_id,
            meeting_dir=None,
            state_mtime=None,
            issues=(validate_err,),
        )
    assert validated_id is not None

    try:
        meeting_dir = store.resolve_session_dir(validated_id, validate_fn=validate_fn)
    except SystemExit as exc:
        return SessionHealth(
            ok=False,
            meeting_id=validated_id,
            meeting_dir=None,
            state_mtime=None,
            issues=(str(exc) or f"cannot resolve session dir for {validated_id!r}",),
        )

    if not meeting_dir.is_dir():
        issues.append(f"meeting directory missing: {meeting_dir}")

    state_path = meeting_dir / store.state_filename
    state_mtime: float | None = None
    if not state_path.is_file():
        issues.append(f"missing {store.state_filename}")
    else:
        state_mtime = state_path.stat().st_mtime
        try:
            store.load_state(meeting_dir)
        except json.JSONDecodeError:
            issues.append(f"invalid JSON in {store.state_filename}")
        except OSError as exc:
            issues.append(f"cannot read {store.state_filename}: {exc}")

    return SessionHealth(
        ok=not issues,
        meeting_id=validated_id,
        meeting_dir=meeting_dir if meeting_dir.is_dir() else None,
        state_mtime=state_mtime,
        issues=tuple(issues),
    )