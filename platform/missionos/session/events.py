"""Per-session append-only JSONL event log (no session field semantics)."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

SESSION_EVENTS_FILE = "events.jsonl"


def session_events_path(session_dir: Path) -> Path:
    return session_dir / SESSION_EVENTS_FILE


def load_session_events(session_dir: Path) -> list[dict[str, Any]]:
    path = session_events_path(session_dir)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def append_session_event(session_dir: Path, event: dict[str, Any]) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_events_path(session_dir)
    with path.open("a", encoding="utf-8") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)