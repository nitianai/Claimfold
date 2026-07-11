"""Canonical JSON serialization and atomic plan writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from missionos.plan.validators import PlanValidationError, validate_plan


def canonical_json_bytes(plan: dict[str, Any]) -> bytes:
    """Deterministic UTF-8 JSON bytes for a validated plan."""
    validate_plan(plan)
    text = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def atomic_write_plan(path: Path, plan: dict[str, Any], *, overwrite: bool = False) -> None:
    """Write meeting_plan.json after validation; refuse overwrite by default."""
    payload = canonical_json_bytes(plan)
    path.parent.mkdir(parents=True, exist_ok=True)

    if overwrite:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            tmp_path.replace(path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        return

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise PlanValidationError(f"refusing to overwrite existing plan: {path}") from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    except Exception:
        path.unlink(missing_ok=True)
        raise