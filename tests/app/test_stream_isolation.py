"""Claims ledger vs meeting events.jsonl stream isolation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from council.adapters.meeting_events import meeting_event_log
from council.claims import append_claim_event
from council.claims.stream_isolation import (
    CLAIM_LEDGER_EVENT_NAMES,
    scan_claim_ledger_file,
    scan_meeting_events_file,
)


def test_meeting_log_rejects_claim_ledger_event_names():
    with tempfile.TemporaryDirectory() as tmp:
        session_dir = Path(tmp) / "meet-20260711-120000"
        session_dir.mkdir()
        log = meeting_event_log(session_dir)
        log.append("guest_completed", guest="qwen", success=True)
        for forbidden in CLAIM_LEDGER_EVENT_NAMES:
            try:
                log.append(forbidden)
                raise AssertionError(f"expected ValueError for {forbidden}")
            except ValueError as exc:
                assert "会议事件流禁止" in str(exc)


def test_append_claim_event_rejects_meeting_event_names():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            append_claim_event(root, {"event": "guest_completed", "claim_id": "clm-000001"})
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "主张账本仅允许" in str(exc)


def test_scan_claim_ledger_accepts_promote_respond_retire():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "claims.jsonl"
        rows = [
            {"event": "PROMOTE", "claim_id": "clm-000001"},
            {"event": "RESPOND", "claim_id": "clm-000001", "response": "SUPPORT"},
            {"event": "RETIRE", "claim_id": "clm-000001"},
        ]
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        assert scan_claim_ledger_file(path) == []


def test_scan_meeting_events_rejects_claim_event_names():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        path.write_text(
            json.dumps({"event": "PROMOTE", "meeting_id": "meet-x"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        errors = scan_meeting_events_file(path)
        assert len(errors) == 1
        assert "PROMOTE" in errors[0]


def test_scan_meeting_events_accepts_session_lifecycle():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        rows = [
            {"event": "meeting_started", "topic": "t"},
            {"event": "claim_responded", "claim_id": "clm-000001"},
        ]
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        assert scan_meeting_events_file(path) == []