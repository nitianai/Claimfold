"""Platform protocol structural compliance tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from missionos.context import ContextPack
from missionos.executor.invoke import invoke_command
from missionos.ledger.store import append_event, load_events
from missionos.protocols import (
    ContextPackInstanceProtocol,
    ContextPackWriterProtocol,
    ExecutorInvokerProtocol,
    LedgerStoreProtocol,
    SessionEventStoreProtocol,
    SessionStoreProtocol,
)
from missionos.session import SessionStore
from missionos.session.events import append_session_event, load_session_events


class _LedgerAdapter:
    @staticmethod
    def append_event(root: Path, event: dict) -> None:
        append_event(root, event)

    @staticmethod
    def load_events(root: Path) -> list[dict]:
        return load_events(root)


def test_session_store_satisfies_protocol():
    store = SessionStore(root=Path("/tmp"))
    assert isinstance(store, SessionStoreProtocol)


def test_context_pack_satisfies_protocols():
    assert isinstance(ContextPack, ContextPackWriterProtocol)
    pack = ContextPack(
        version="1.0",
        scope="s",
        topic="t",
        generated_at="2026-01-01T00:00:00Z",
        body_path="market_context.md",
        checksum="abc",
        metadata={},
    )
    assert isinstance(pack, ContextPackInstanceProtocol)


def test_ledger_module_satisfies_protocol():
    adapter = _LedgerAdapter()
    assert isinstance(adapter, LedgerStoreProtocol)


def test_invoke_command_satisfies_protocol():
    assert isinstance(invoke_command, ExecutorInvokerProtocol)


def test_session_events_satisfies_protocol():
    class _SessionEventAdapter:
        @staticmethod
        def append_session_event(session_dir: Path, event: dict) -> None:
            append_session_event(session_dir, event)

        @staticmethod
        def load_session_events(session_dir: Path) -> list[dict]:
            return load_session_events(session_dir)

    assert isinstance(_SessionEventAdapter(), SessionEventStoreProtocol)


def test_protocol_session_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = SessionStore(root=root)
        session_dir = store.resolve_session_dir("meet-20260711-120000")
        session_dir.mkdir(parents=True)
        store.write_pointer("meet-20260711-120000")
        store.save_state(session_dir, {"topic": "protocol smoke"})
        assert store.read_pointer() == "meet-20260711-120000"
        assert store.load_state(session_dir)["topic"] == "protocol smoke"