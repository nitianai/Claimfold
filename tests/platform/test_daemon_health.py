"""Platform daemon health tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from missionos.daemon import check_session_health
from missionos.protocols import SessionStoreProtocol
from missionos.session import SessionStore


def test_session_store_satisfies_daemon_contract():
    store = SessionStore(root=Path("/tmp"))
    assert isinstance(store, SessionStoreProtocol)


def test_daemon_detects_missing_state_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = SessionStore(root=root)
        meeting_id = "meet-20260711-140000"
        meeting_dir = root / "meetings" / meeting_id
        meeting_dir.mkdir(parents=True)
        store.write_pointer(meeting_id)

        health = check_session_health(store)
        assert not health.ok
        assert any("meeting_state.json" in issue for issue in health.issues)