"""Floor protocol and annotation tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from council.interactive.annotations import build_session_annotations
from council.interactive.protocol import (
    apply_floor_requests_to_queue,
    apply_pending_interrupts,
    refresh_queue_from_pending_requests,
    register_floor_request,
    register_interrupt,
)
from council.interactive.state import ensure_interactive_fields, resolve_max_turns
from missionos.session.events import append_session_event


def test_apply_floor_requests_reorders_by_urgency():
    state = {"floor_requests": []}
    ensure_interactive_fields(state)
    register_floor_request(state, guest="qoder", urgency=2)
    register_floor_request(state, guest="codex", urgency=0)
    ordered = apply_floor_requests_to_queue(state, ["codex", "qoder"])
    assert ordered[0] == "qoder"


def test_apply_floor_requests_adds_guest_outside_base_queue():
    state = {"floor_requests": []}
    ensure_interactive_fields(state)
    register_floor_request(state, guest="codex", urgency=2, build_on="msg-001-01-laguna")
    ordered = apply_floor_requests_to_queue(state, ["laguna"])
    assert ordered == ["codex", "laguna"]
    assert state["guest_build_on"]["codex"] == "msg-001-01-laguna"


def test_apply_floor_requests_preserves_build_on_map():
    state = {"floor_requests": []}
    ensure_interactive_fields(state)
    register_floor_request(state, guest="qoder", urgency=1, build_on="msg-001-01-codex")
    apply_floor_requests_to_queue(state, ["codex", "qoder"])
    assert state["guest_build_on"]["qoder"] == "msg-001-01-codex"


def test_resolve_max_turns_defaults_to_guest_count():
    assert resolve_max_turns({"max_turns_per_round": 0}, 3) == 3
    assert resolve_max_turns({"max_turns_per_round": 5}, 3) == 5


def test_refresh_queue_mid_session():
    state = {
        "speaking_queue": ["codex", "qoder"],
        "floor_requests": [],
        "pending_interrupts": [],
    }
    ensure_interactive_fields(state)
    register_floor_request(state, guest="qoder", urgency=9)
    assert refresh_queue_from_pending_requests(state)
    assert state["speaking_queue"][0] == "qoder"
    assert state["floor_requests"] == []


def test_pending_interrupts_become_floor_requests():
    state = {"floor_requests": [], "pending_interrupts": []}
    ensure_interactive_fields(state)
    register_interrupt(state, guest="grok", target_guest="codex", target_message_id="msg-1")
    apply_pending_interrupts(state)
    assert state["pending_interrupts"] == []
    assert any(r["guest"] == "grok" and r["urgency"] == 10 for r in state["floor_requests"])


def test_build_session_annotations_from_claim_and_threads():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-test"
        meeting_dir.mkdir()
        append_session_event(
            meeting_dir,
            {
                "event": "claim_responded",
                "guest": "codex",
                "claim_id": "clm-001",
                "response": "SUPPORT",
            },
        )
        state = {
            "session_messages": [
                {"message_id": "msg-1", "guest": "grok", "reply_to": "msg-0", "excerpt": "同意"}
            ],
            "active_threads": [
                {"thread_id": "th-1", "participants": ["codex", "grok"], "topic": "黄金", "build_on": "msg-0"}
            ],
        }
        anns = build_session_annotations(meeting_dir, state)
        types = {a["type"] for a in anns}
        assert "AGREE" in types
        assert "BUILD_ON" in types
        assert "THREAD" in types