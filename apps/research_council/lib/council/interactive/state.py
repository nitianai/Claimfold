"""Interactive session state helpers."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from missionos.session.events import load_session_events

INTERACTIVE_DEFAULTS: dict[str, Any] = {
    "interaction_mode": "turn_based",
    "session_status": "idle",
    "event_seq": 0,
    "current_speaker": None,
    "speaking_queue": [],
    "floor_turn": 0,
    "interactive_round": None,
    "interactive_guests": [],
    "interactive_entries": [],
    "session_messages": [],
    "context_cursor": 0,
    "state_version": 1,
    "pending_interrupts": [],
    "active_threads": [],
    "max_turns_per_round": 0,
    "floor_requests": [],
    "guest_build_on": {},
}


def is_interactive_mode(state: dict[str, Any]) -> bool:
    return state.get("meeting_mode") == "interactive"


def ensure_interactive_fields(state: dict[str, Any]) -> None:
    for key, default in INTERACTIVE_DEFAULTS.items():
        if key not in state:
            state[key] = copy.deepcopy(default) if isinstance(default, list) else default


def bump_event_seq(state: dict[str, Any]) -> int:
    state["event_seq"] = int(state.get("event_seq") or 0) + 1
    return state["event_seq"]


def sync_context_cursor(meeting_dir: Path, state: dict[str, Any]) -> int:
    cursor = len(load_session_events(meeting_dir))
    state["context_cursor"] = cursor
    return cursor


def resolve_max_turns(state: dict[str, Any], guest_count: int) -> int:
    configured = int(state.get("max_turns_per_round") or 0)
    if configured > 0:
        return configured
    return max(guest_count, 1)


def init_round_queue(state: dict[str, Any], guests: list[str]) -> None:
    state["speaking_queue"] = list(guests)
    state["current_speaker"] = None
    state["floor_turn"] = 0
    state["session_messages"] = []
    state["interactive_entries"] = []
    state["interactive_guests"] = list(guests)
    state["guest_build_on"] = {}


def pop_next_speaker(state: dict[str, Any]) -> str | None:
    queue = list(state.get("speaking_queue") or [])
    if not queue:
        state["current_speaker"] = None
        return None
    guest = queue.pop(0)
    state["speaking_queue"] = queue
    state["current_speaker"] = guest
    state["floor_turn"] = int(state.get("floor_turn") or 0) + 1
    return guest


def session_inspect_payload(state: dict[str, Any]) -> dict[str, Any]:
    ensure_interactive_fields(state)
    return {
        "meeting_id": state.get("meeting_id"),
        "meeting_mode": state.get("meeting_mode"),
        "interaction_mode": state.get("interaction_mode"),
        "session_status": state.get("session_status"),
        "round": state.get("round"),
        "interactive_round": state.get("interactive_round"),
        "current_speaker": state.get("current_speaker"),
        "speaking_queue": list(state.get("speaking_queue") or []),
        "floor_turn": state.get("floor_turn"),
        "event_seq": state.get("event_seq"),
        "session_messages": list(state.get("session_messages") or []),
        "owner_required": state.get("owner_required"),
        "selected_guests": state.get("selected_guests"),
        "active_threads": list(state.get("active_threads") or []),
        "context_cursor": state.get("context_cursor"),
        "max_turns_per_round": state.get("max_turns_per_round"),
        "pending_interrupts": list(state.get("pending_interrupts") or []),
    }