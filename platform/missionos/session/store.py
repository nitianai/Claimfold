"""Session JSON state and pointer I/O (no Council field semantics)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from missionos.utils import atomic_write_json, resolve_meeting_path


def load_json_state(session_dir: Path, *, filename: str = "meeting_state.json") -> dict[str, Any]:
    path = session_dir / filename
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json_state(
    session_dir: Path,
    state: dict[str, Any],
    *,
    filename: str = "meeting_state.json",
) -> None:
    atomic_write_json(session_dir / filename, state)


def read_pointer(pointer_path: Path) -> str:
    return pointer_path.read_text(encoding="utf-8").strip()


def write_pointer(pointer_path: Path, session_id: str) -> None:
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(session_id.strip() + "\n", encoding="utf-8")


def resolve_session_dir(
    sessions_dir: Path,
    session_id: str,
    *,
    validate_fn: Callable[[str], str] | None = None,
) -> Path:
    if validate_fn is not None:
        session_id = validate_fn(session_id)
    return resolve_meeting_path(sessions_dir, session_id)


@dataclass
class SessionStore:
    """Parameterized session root, pointer, and JSON state I/O."""

    root: Path
    pointer_name: str = ".current_meeting"
    sessions_dir_name: str = "meetings"
    state_filename: str = "meeting_state.json"

    @property
    def pointer_path(self) -> Path:
        return self.root / self.pointer_name

    @property
    def sessions_dir(self) -> Path:
        return self.root / self.sessions_dir_name

    def load_state(self, session_dir: Path) -> dict[str, Any]:
        return load_json_state(session_dir, filename=self.state_filename)

    def save_state(self, session_dir: Path, state: dict[str, Any]) -> None:
        save_json_state(session_dir, state, filename=self.state_filename)

    def read_pointer(self) -> str:
        return read_pointer(self.pointer_path)

    def write_pointer(self, session_id: str) -> None:
        write_pointer(self.pointer_path, session_id)

    def resolve_session_dir(
        self,
        session_id: str,
        *,
        validate_fn: Callable[[str], str] | None = None,
    ) -> Path:
        return resolve_session_dir(
            self.sessions_dir,
            session_id,
            validate_fn=validate_fn,
        )