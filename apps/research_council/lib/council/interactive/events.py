"""Interactive session event publishers."""

from __future__ import annotations

from typing import Any

from council.adapters.meeting_events import MeetingEventLog


def publish_session_started(
    log: MeetingEventLog,
    *,
    round_num: int,
    guests: list[str],
    interaction_mode: str = "turn_based",
    event_seq: int,
) -> None:
    log.append(
        "session_started",
        round=round_num,
        guests=guests,
        interaction_mode=interaction_mode,
        event_seq=event_seq,
    )


def publish_floor_granted(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest: str,
    turn: int,
    event_seq: int,
) -> None:
    log.append(
        "floor_granted",
        round=round_num,
        guest=guest,
        turn=turn,
        event_seq=event_seq,
    )


def publish_message_committed(
    log: MeetingEventLog,
    entry: dict[str, Any],
    *,
    message_id: str,
    turn: int,
    reply_to: str | None,
    event_seq: int,
) -> None:
    log.append(
        "message_committed",
        round=entry.get("round"),
        guest=entry.get("guest", ""),
        turn=turn,
        message_id=message_id,
        reply_to=reply_to,
        success=bool(entry.get("success")),
        duration_s=entry.get("duration_s"),
        raw_output_path=entry.get("raw_output_path", ""),
        summary_json_path=entry.get("summary_json_path", ""),
        event_seq=event_seq,
    )


def publish_floor_yielded(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest: str,
    turn: int,
    event_seq: int,
) -> None:
    log.append(
        "floor_yielded",
        round=round_num,
        guest=guest,
        turn=turn,
        event_seq=event_seq,
    )


def publish_session_paused(
    log: MeetingEventLog,
    *,
    round_num: int,
    remaining_queue: list[str],
    event_seq: int,
) -> None:
    log.append(
        "session_paused",
        round=round_num,
        remaining_queue=remaining_queue,
        event_seq=event_seq,
    )


def publish_floor_requested(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest: str,
    urgency: int = 0,
    build_on: str | None = None,
    request_type: str = "SPEAK",
    event_seq: int,
) -> None:
    log.append(
        "floor_requested",
        round=round_num,
        guest=guest,
        urgency=urgency,
        build_on=build_on,
        request_type=request_type,
        event_seq=event_seq,
    )


def publish_interrupt_requested(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest: str,
    target_guest: str,
    target_message_id: str | None = None,
    event_seq: int,
) -> None:
    log.append(
        "interrupt_requested",
        round=round_num,
        guest=guest,
        target_guest=target_guest,
        target_message_id=target_message_id,
        event_seq=event_seq,
    )


def publish_message_proposed(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest: str,
    turn: int,
    message_id: str,
    reply_to: str | None,
    event_seq: int,
) -> None:
    log.append(
        "message_proposed",
        round=round_num,
        guest=guest,
        turn=turn,
        message_id=message_id,
        reply_to=reply_to,
        event_seq=event_seq,
    )


def publish_context_observed(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest: str,
    context_cursor: int,
    event_seq: int,
) -> None:
    log.append(
        "context_observed",
        round=round_num,
        guest=guest,
        context_cursor=context_cursor,
        event_seq=event_seq,
    )


def publish_session_ended(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest_count: int,
    duration_s: float,
    event_seq: int,
) -> None:
    log.append(
        "session_ended",
        round=round_num,
        guest_count=guest_count,
        duration_s=duration_s,
        event_seq=event_seq,
    )