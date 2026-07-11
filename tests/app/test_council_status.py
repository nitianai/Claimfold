"""Council status builder tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from council.web.chat import build_council_status
from missionos.session.events import append_session_event


def test_build_council_status_tracks_running_and_done():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-130000"
        meeting_dir.mkdir()
        append_session_event(
            meeting_dir,
            {
                "event": "round_started",
                "round": 2,
                "guests": ["codex", "laguna"],
                "ts": "2026-07-11T13:00:00Z",
            },
        )
        append_session_event(
            meeting_dir,
            {
                "event": "guest_completed",
                "round": 2,
                "guest": "codex",
                "success": True,
                "duration_s": 15.2,
                "ts": "2026-07-11T13:01:00Z",
            },
        )
        state = {"round": 2, "selected_guests": ["codex", "laguna"]}
        guests = {
            "codex": {"role": "Auditor"},
            "laguna": {"role": "Grok"},
        }
        statuses = build_council_status(
            meeting_dir,
            state,
            guests,
            task={"running": True, "task": "run_parallel"},
        )
        by_guest = {s["guest"]: s for s in statuses}
        assert by_guest["codex"]["status"] == "done"
        assert by_guest["laguna"]["status"] == "running"