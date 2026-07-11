"""Annotation projection — AGREE/DISAGREE/QUESTION from claims + threads (read-only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from missionos.session.events import load_session_events

_RESPONSE_MAP = {
    "SUPPORT": "AGREE",
    "CHALLENGE": "DISAGREE",
    "DEFER": "QUESTION",
    "RETIRE": "DISAGREE",
}


def build_session_annotations(meeting_dir: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Project annotations from claim_responded events and active_threads (no new writes)."""
    annotations: list[dict[str, Any]] = []
    for ev in load_session_events(meeting_dir):
        if ev.get("event") != "claim_responded":
            continue
        response = str(ev.get("response", "")).upper()
        annotations.append(
            {
                "type": _RESPONSE_MAP.get(response, response or "NOTE"),
                "guest": ev.get("guest", ""),
                "claim_id": ev.get("claim_id", ""),
                "evidence_ref": ev.get("evidence_ref", ""),
                "source": "claim_responded",
            }
        )
    for msg in state.get("session_messages") or []:
        if msg.get("reply_to"):
            annotations.append(
                {
                    "type": "BUILD_ON",
                    "guest": msg.get("guest", ""),
                    "target_message_id": msg.get("reply_to"),
                    "excerpt": (msg.get("excerpt") or "")[:120],
                    "source": "session_message",
                }
            )
    for th in state.get("active_threads") or []:
        annotations.append(
            {
                "type": "THREAD",
                "thread_id": th.get("thread_id"),
                "participants": th.get("participants") or [],
                "topic": th.get("topic", ""),
                "build_on": th.get("build_on"),
                "source": "active_threads",
            }
        )
    return annotations