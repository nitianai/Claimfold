"""Per-session events.jsonl platform tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from missionos.session.events import (
    SESSION_EVENTS_FILE,
    append_session_event,
    load_session_events,
    session_events_path,
)


def test_append_and_load_session_events():
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp) / "meet-20260711-120000"
        session_dir.mkdir(parents=True)

        append_session_event(session_dir, {"event": "test", "n": 1})
        append_session_event(session_dir, {"event": "test", "n": 2})

        events = load_session_events(session_dir)
        assert len(events) == 2
        assert events[0]["n"] == 1
        assert events[1]["n"] == 2
        assert session_events_path(session_dir).name == SESSION_EVENTS_FILE


def test_load_session_events_empty_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp) / "meet-20260711-120000"
        assert load_session_events(session_dir) == []


def test_session_events_skip_malformed_lines():
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp) / "meet-20260711-120000"
        session_dir.mkdir(parents=True)
        path = session_events_path(session_dir)
        path.write_text(
            json.dumps({"event": "ok"}) + "\n"
            + "not-json\n"
            + json.dumps({"event": "ok2"}) + "\n",
            encoding="utf-8",
        )
        events = load_session_events(session_dir)
        assert len(events) == 2
        assert events[0]["event"] == "ok"
        assert events[1]["event"] == "ok2"