"""Floor protocol — request / yield / interrupt / build_on thread management."""

from __future__ import annotations

import uuid
from typing import Any


def _thread_id_for_message(message_id: str) -> str:
    return f"th-{message_id}"


def register_floor_request(
    state: dict[str, Any],
    *,
    guest: str,
    urgency: int = 0,
    build_on: str | None = None,
    request_type: str = "SPEAK",
) -> dict[str, Any]:
    req = {
        "guest": guest,
        "urgency": int(urgency),
        "build_on": build_on,
        "request_type": request_type,
    }
    requests = list(state.get("floor_requests") or [])
    requests = [r for r in requests if r.get("guest") != guest]
    requests.append(req)
    state["floor_requests"] = requests
    if build_on:
        _ensure_thread(state, guest=guest, build_on=build_on)
    return req


def register_interrupt(
    state: dict[str, Any],
    *,
    guest: str,
    target_guest: str,
    target_message_id: str | None = None,
) -> dict[str, Any]:
    interrupt = {
        "guest": guest,
        "target_guest": target_guest,
        "target_message_id": target_message_id,
    }
    pending = list(state.get("pending_interrupts") or [])
    pending.append(interrupt)
    state["pending_interrupts"] = pending
    return interrupt


def yield_floor(state: dict[str, Any], guest: str) -> bool:
    if state.get("current_speaker") != guest:
        return False
    state["current_speaker"] = None
    return True


def _ensure_thread(state: dict[str, Any], *, guest: str, build_on: str) -> dict[str, Any]:
    threads = list(state.get("active_threads") or [])
    for th in threads:
        if th.get("build_on") == build_on and guest in (th.get("participants") or []):
            return th
    root_msg = build_on
    topic = ""
    for msg in state.get("session_messages") or []:
        if msg.get("message_id") == build_on:
            topic = (msg.get("excerpt") or "")[:80]
            break
    thread = {
        "thread_id": _thread_id_for_message(root_msg),
        "build_on": build_on,
        "participants": [guest],
        "topic": topic or build_on,
    }
    threads.append(thread)
    state["active_threads"] = threads
    return thread


def apply_pending_interrupts(state: dict[str, Any]) -> None:
    """Convert pending interrupts into high-urgency floor requests, then clear."""
    for intr in list(state.get("pending_interrupts") or []):
        register_floor_request(
            state,
            guest=str(intr.get("guest", "")),
            urgency=10,
            build_on=intr.get("target_message_id"),
            request_type="CHALLENGE",
        )
    state["pending_interrupts"] = []


def refresh_queue_from_pending_requests(state: dict[str, Any]) -> bool:
    """Re-merge floor/interrupt requests into the remaining queue (mid-session)."""
    if not (state.get("floor_requests") or state.get("pending_interrupts")):
        return False
    apply_pending_interrupts(state)
    remaining = list(state.get("speaking_queue") or [])
    merged = apply_floor_requests_to_queue(state, remaining)
    state["speaking_queue"] = merged
    state["floor_requests"] = []
    return True


def apply_floor_requests_to_queue(state: dict[str, Any], base_queue: list[str]) -> list[str]:
    """Merge floor requests into speaking queue (higher urgency first, stable within tier)."""
    requests = sorted(
        state.get("floor_requests") or [],
        key=lambda r: (-int(r.get("urgency") or 0), base_queue.index(r["guest"]) if r["guest"] in base_queue else 999),
    )
    build_on_map: dict[str, str] = {}
    ordered: list[str] = []
    seen: set[str] = set()
    for req in requests:
        g = req.get("guest", "")
        if g and g not in seen:
            ordered.append(g)
            seen.add(g)
            if req.get("build_on"):
                build_on_map[g] = str(req["build_on"])
    for g in base_queue:
        if g not in seen:
            ordered.append(g)
            seen.add(g)
    state["guest_build_on"] = build_on_map
    return ordered


def record_message_thread(
    state: dict[str, Any],
    *,
    message_id: str,
    guest: str,
    reply_to: str | None,
) -> None:
    if not reply_to:
        return
    threads = list(state.get("active_threads") or [])
    for th in threads:
        if th.get("build_on") == reply_to or th.get("thread_id") == _thread_id_for_message(reply_to):
            parts = list(th.get("participants") or [])
            if guest not in parts:
                parts.append(guest)
            th["participants"] = parts
            th["latest_message_id"] = message_id
            state["active_threads"] = threads
            return
    threads.append(
        {
            "thread_id": f"th-{uuid.uuid4().hex[:8]}",
            "build_on": reply_to,
            "participants": [guest],
            "topic": reply_to,
            "latest_message_id": message_id,
        }
    )
    state["active_threads"] = threads