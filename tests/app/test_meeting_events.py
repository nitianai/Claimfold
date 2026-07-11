"""Meeting event stream (events.jsonl) integration tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

from council.adapters.meeting_events import (
    MEETING_EVENT_SCHEMA,
    meeting_event_log,
    publish_context_written,
    publish_meeting_started,
    publish_round_started,
    publish_state_merged,
)
from council.runners.parallel import run_one_parallel_round
from missionos.context import ContextPack
from missionos.session.events import load_session_events


def _seed_meeting(meeting_dir: Path, *, selected: list[str] | None = None) -> None:
    meeting_dir.mkdir(parents=True, exist_ok=True)
    (meeting_dir / "raw").mkdir(exist_ok=True)
    (meeting_dir / "summaries").mkdir(exist_ok=True)
    (meeting_dir / "prompts").mkdir(exist_ok=True)
    state = {
        "meeting_id": meeting_dir.name,
        "topic": "黄金一周走势",
        "owner_question": "黄金一周走势",
        "meeting_mode": "research",
        "round": 0,
        "status": "running",
        "owner_required": False,
        "max_round_before_owner": 3,
        "max_rounds": 3,
        "stale_round_limit": 5,
        "guest_turns_since_owner": 0,
        "rounds_since_owner": 0,
        "confirmed_points": [],
        "conflicts": [],
        "open_questions": [],
        "guest_summaries": {},
        "owner_views": [],
        "next_speaker": "qwen",
        "next_question": "黄金一周走势",
        "history": [],
        "stop_reason": "",
        "output_format": "research",
        "round_mode": "parallel",
        "selected_guests": selected or ["codex", "qoder"],
        "current_focus": "黄金、美元",
        "stop_recommendation": "",
        "positions": {},
        "challenges": [],
        "verifications": [],
        "round_records": [],
    }
    import json

    (meeting_dir / "meeting_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ContextPack.write(
        meeting_dir / "context",
        body="# Market Context\n\nGold 4100.",
        scope="黄金、美元",
        topic="黄金一周走势",
        generated_at="2026-07-11T12:00:00Z",
    )


def test_meeting_event_log_schema():
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp) / "meet-20260711-120000"
        session_dir.mkdir(parents=True)
        log = meeting_event_log(session_dir)
        publish_meeting_started(log, {"topic": "test", "meeting_mode": "research", "max_rounds": 3})

        events = log.load()
        assert len(events) == 1
        ev = events[0]
        assert ev["schema_version"] == MEETING_EVENT_SCHEMA
        assert ev["event"] == "meeting_started"
        assert ev["meeting_id"] == session_dir.name
        assert "ts" in ev
        assert ev["topic"] == "test"


def test_publish_context_written_event():
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp) / "meet-20260711-120000"
        session_dir.mkdir(parents=True)
        log = meeting_event_log(session_dir)
        publish_context_written(
            log,
            scope="黄金",
            checksum="abc123",
            used_mock=False,
        )
        ev = log.load()[0]
        assert ev["event"] == "context_written"
        assert ev["scope"] == "黄金"
        assert ev["checksum"] == "abc123"


def test_parallel_round_writes_event_stream():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_dir = root / "meetings" / "meet-20260711-120000"
        _seed_meeting(meeting_dir)

        prev_root = os.environ.get("COUNCIL_DATA_ROOT")
        prev_mock = os.environ.get("COUNCIL_MOCK")
        os.environ["COUNCIL_DATA_ROOT"] = str(root)
        os.environ["COUNCIL_MOCK"] = "1"

        def fake_guest(_cmd, _prompt, **kwargs):
            guest = kwargs.get("guest", "guest")
            return f"# Guest {guest}\n\n判断：mock\n", True

        summary = (
            "## confirmed_points\n- 金价4100\n\n"
            "## conflicts\n- 无\n\n"
            "## open_questions\n- 无\n\n"
            "## guest_position_summary\nmock position\n"
        )
        try:
            with mock.patch("council.runners.parallel.invoke_cli", side_effect=fake_guest), mock.patch(
                "council.runners.parallel.run_summarizer_for_guest",
                return_value=(summary, False),
            ):
                run_one_parallel_round(meeting_dir, quiet=True)
        finally:
            if prev_root is None:
                os.environ.pop("COUNCIL_DATA_ROOT", None)
            else:
                os.environ["COUNCIL_DATA_ROOT"] = prev_root
            if prev_mock is None:
                os.environ.pop("COUNCIL_MOCK", None)
            else:
                os.environ["COUNCIL_MOCK"] = prev_mock

        events = load_session_events(meeting_dir)
        types = [e["event"] for e in events]
        assert "round_started" in types
        assert types.count("guest_completed") == 2
        assert "state_merged" in types

        round_started = next(e for e in events if e["event"] == "round_started")
        assert round_started["round"] == 1
        assert round_started["guests"] == ["codex", "qoder"]
        assert round_started["snapshot_meeting_id"] == meeting_dir.name

        state_merged = next(e for e in events if e["event"] == "state_merged")
        assert state_merged["round"] == 1
        assert state_merged["guest_count"] == 2