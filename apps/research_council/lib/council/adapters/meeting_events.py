"""Meeting event stream — append-only session events.jsonl (App semantics)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from council.claims.stream_isolation import assert_meeting_event_type
from missionos.session.events import append_session_event, load_session_events
from missionos.utils import utc_now

MEETING_EVENT_SCHEMA = "1.0"


class MeetingEventLog:
    """Typed publisher for council meeting lifecycle events."""

    def __init__(self, session_dir: Path, meeting_id: str) -> None:
        self.session_dir = session_dir
        self.meeting_id = meeting_id

    def append(self, event_type: str, **payload: Any) -> None:
        assert_meeting_event_type(event_type)
        event = {
            "schema_version": MEETING_EVENT_SCHEMA,
            "event": event_type,
            "meeting_id": self.meeting_id,
            "ts": utc_now(),
            **payload,
        }
        append_session_event(self.session_dir, event)

    def load(self) -> list[dict[str, Any]]:
        return load_session_events(self.session_dir)


def meeting_event_log(session_dir: Path, meeting_id: str | None = None) -> MeetingEventLog:
    return MeetingEventLog(session_dir, meeting_id or session_dir.name)


def publish_meeting_started(log: MeetingEventLog, state: dict[str, Any]) -> None:
    log.append(
        "meeting_started",
        topic=state.get("topic", ""),
        meeting_mode=state.get("meeting_mode", ""),
        max_rounds=state.get("max_rounds"),
    )


def publish_context_written(
    log: MeetingEventLog,
    *,
    scope: str,
    checksum: str,
    used_mock: bool,
    body_path: str = "context/market_context.md",
) -> None:
    log.append(
        "context_written",
        scope=scope,
        checksum=checksum,
        used_mock=used_mock,
        body_path=body_path,
    )


def publish_round_started(
    log: MeetingEventLog,
    *,
    round_num: int,
    guests: list[str],
    snapshot_meeting_id: str,
) -> None:
    log.append(
        "round_started",
        round=round_num,
        guests=guests,
        snapshot_meeting_id=snapshot_meeting_id,
    )


def publish_guest_completed(log: MeetingEventLog, entry: dict[str, Any]) -> None:
    log.append(
        "guest_completed",
        round=entry.get("round"),
        guest=entry.get("guest", ""),
        success=bool(entry.get("success")),
        duration_s=entry.get("duration_s"),
        used_mock_guest=bool(entry.get("used_mock_guest")),
        used_mock_summarizer=bool(entry.get("used_mock_summarizer")),
        confirmed_points_added=entry.get("confirmed_points_added", 0),
        conflicts_added=entry.get("conflicts_added", 0),
        open_questions_added=entry.get("open_questions_added", 0),
        raw_output_path=entry.get("raw_output_path", ""),
        summary_json_path=entry.get("summary_json_path", ""),
        error=entry.get("error", ""),
    )


def publish_claim_responded(log: MeetingEventLog, claim_event: dict[str, Any]) -> None:
    log.append(
        "claim_responded",
        claim_id=claim_event.get("claim_id", ""),
        response=claim_event.get("response", ""),
        guest=claim_event.get("guest", ""),
        meeting_id=claim_event.get("meeting_id", log.meeting_id),
        evidence_ref=claim_event.get("evidence_ref", ""),
    )


def publish_state_merged(
    log: MeetingEventLog,
    *,
    round_num: int,
    confirmed_points_added: int,
    conflicts_added: int,
    open_questions_added: int,
    duration_s: float,
    guest_count: int,
) -> None:
    log.append(
        "state_merged",
        round=round_num,
        confirmed_points_added=confirmed_points_added,
        conflicts_added=conflicts_added,
        open_questions_added=open_questions_added,
        duration_s=duration_s,
        guest_count=guest_count,
    )