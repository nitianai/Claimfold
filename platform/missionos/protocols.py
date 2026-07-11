"""Structural protocols for Platform ↔ App contracts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from missionos.executor.invoke import InvokeResult


@runtime_checkable
class SessionStoreProtocol(Protocol):
    state_filename: str

    @property
    def pointer_path(self) -> Path: ...

    @property
    def sessions_dir(self) -> Path: ...

    def load_state(self, session_dir: Path) -> dict[str, Any]: ...

    def save_state(self, session_dir: Path, state: dict[str, Any]) -> None: ...

    def read_pointer(self) -> str: ...

    def write_pointer(self, session_id: str) -> None: ...

    def resolve_session_dir(
        self,
        session_id: str,
        *,
        validate_fn: Callable[[str], str] | None = None,
    ) -> Path: ...


@runtime_checkable
class ContextPackWriterProtocol(Protocol):
    @classmethod
    def write(
        cls,
        context_dir: Path,
        *,
        body: str,
        scope: str,
        topic: str,
        generated_at: str,
        metadata: dict[str, Any] | None = None,
        body_filename: str = ...,
        legacy_json_filename: str = ...,
    ) -> tuple[Path, Path, Path]: ...


@runtime_checkable
class ContextPackInstanceProtocol(Protocol):
    version: str
    scope: str
    topic: str
    generated_at: str
    body_path: str
    checksum: str
    metadata: dict[str, Any]

    def read_body(self, context_dir: Path) -> str: ...

    def verify_checksum(self, context_dir: Path) -> bool: ...


@runtime_checkable
class LedgerStoreProtocol(Protocol):
    def append_event(self, root: Path, event: dict[str, Any]) -> None: ...

    def load_events(self, root: Path) -> list[dict[str, Any]]: ...


@runtime_checkable
class SessionEventStoreProtocol(Protocol):
    def append_session_event(self, session_dir: Path, event: dict[str, Any]) -> None: ...

    def load_session_events(self, session_dir: Path) -> list[dict[str, Any]]: ...


@runtime_checkable
class ExecutorInvokerProtocol(Protocol):
    def __call__(
        self,
        command: str | Sequence[str],
        *,
        stdin: str = "",
        cwd: str | None = None,
        timeout_seconds: int = 600,
    ) -> InvokeResult: ...