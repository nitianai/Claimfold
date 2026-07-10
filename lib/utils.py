"""Shared utilities for Council Engine."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEETING_ID_RE = re.compile(r"^meet-\d{8}-\d{6}$")

_RELAX_CLI = False


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def relax_cli_enabled() -> bool:
    if _RELAX_CLI:
        return True
    return os.environ.get("COUNCIL_RELAX", "").strip().lower() in ("1", "true", "yes")


def set_relax_cli(enabled: bool) -> None:
    global _RELAX_CLI
    _RELAX_CLI = enabled


def strict_cli_enabled() -> bool:
    """Default fail-closed; opt out via --relax or COUNCIL_RELAX=1."""
    if relax_cli_enabled():
        return False
    if os.environ.get("COUNCIL_STRICT", "").strip().lower() in ("0", "false", "no"):
        return False
    return True


def validate_meeting_id(meeting_id: str) -> str:
    mid = (meeting_id or "").strip()
    if not MEETING_ID_RE.match(mid):
        raise SystemExit(f"Invalid meeting id: {mid!r} (expected meet-YYYYMMDD-HHMMSS)")
    return mid


def resolve_meeting_path(meetings_dir: Path, meeting_id: str) -> Path:
    mid = validate_meeting_id(meeting_id)
    root = meetings_dir.resolve()
    path = (root / mid).resolve()
    if not path.is_relative_to(root):
        raise SystemExit(f"Meeting path escapes meetings dir: {mid}")
    return path


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def clamp_int(value: Any, *, default: int, min_val: int, max_val: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_val, min(n, max_val))