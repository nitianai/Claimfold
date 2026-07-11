"""SessionStore and safe_artifact_path platform tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from missionos.session import SessionStore, safe_artifact_path
from missionos.utils import validate_meeting_id


def test_session_store_pointer_and_state_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = SessionStore(root=root)
        session_id = "meet-20260711-120000"
        session_dir = store.resolve_session_dir(session_id, validate_fn=validate_meeting_id)
        session_dir.mkdir(parents=True)

        store.write_pointer(session_id)
        assert store.read_pointer() == session_id

        payload = {"topic": "gold", "round": 1}
        store.save_state(session_dir, payload)
        loaded = store.load_state(session_dir)
        assert loaded == payload


def test_safe_artifact_path_under_session_dir():
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp) / "meet-20260711-120000"
        session_dir.mkdir()
        path = safe_artifact_path(session_dir, "prompts", "grok", "01")
        assert path == session_dir.resolve() / "prompts" / "round-01-grok"
        assert path.is_relative_to(session_dir.resolve())


def test_safe_artifact_path_rejects_invalid_segments():
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp)
        for bad in ("", "bad/id", "..", "round/../x"):
            try:
                safe_artifact_path(session_dir, bad, "grok", "01")
                raise AssertionError(f"expected SystemExit for {bad!r}")
            except SystemExit:
                pass


def test_session_store_load_json_state_via_functions():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = SessionStore(root=root, state_filename="custom_state.json")
        session_dir = root / "meetings" / "meet-20260711-120000"
        session_dir.mkdir(parents=True)
        (session_dir / "custom_state.json").write_text(
            json.dumps({"ok": True}) + "\n",
            encoding="utf-8",
        )
        assert store.load_state(session_dir) == {"ok": True}