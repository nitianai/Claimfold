"""Web API contract — guest_slots / HITL / council_status alignment."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from council.web.chat import build_council_status
from council.web.role_cards import card_guest_id
from council.web.service import CouncilWebService
from missionos.context import ContextPack
from missionos.session.events import append_session_event


def _seed_meeting(meeting_dir: Path, *, state_extra: dict | None = None) -> dict:
    meeting_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("raw", "summaries", "prompts", "errors"):
        (meeting_dir / sub).mkdir(exist_ok=True)
    state = {
        "meeting_id": meeting_dir.name,
        "topic": "黄金一周走势",
        "owner_question": "黄金一周走势",
        "meeting_mode": "research",
        "round": 1,
        "status": "running",
        "owner_required": True,
        "failure_policy": "fail_fast",
        "max_round_before_owner": 3,
        "max_rounds": 12,
        "selected_guests": [],
        "confirmed_points": [],
        "conflicts": [],
        "open_questions": [],
        "guest_summaries": {},
        "owner_views": [],
        "history": [],
        "guest_slots": {
            "r001:codex": {
                "round": 1,
                "guest_id": "codex",
                "phase": "Failed",
                "attempts": 1,
                "max_retries": 1,
                "message": "cli exploded",
                "artifact": {"raw": "raw/round-001-codex.md"},
            },
            "r001:qoder": {
                "round": 1,
                "guest_id": "qoder",
                "phase": "Skipped",
                "attempts": 0,
                "max_retries": 1,
                "message": "fail_fast: prior guest failed",
                "artifact": {},
            },
        },
        "hitl": {
            "every_n_rounds": 3,
            "require_before_promote": False,
            "open": True,
            "reason": "guest_failure",
            "round": 1,
        },
        "partial_warnings": [],
    }
    if state_extra:
        state.update(state_extra)
    (meeting_dir / "meeting_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ContextPack.write(
        meeting_dir / "context",
        body="# Market Context\n\nGold 4100.",
        scope="黄金",
        topic="黄金一周走势",
        generated_at="2026-07-11T12:00:00Z",
    )
    append_session_event(
        meeting_dir,
        {
            "event": "round_started",
            "round": 1,
            "guests": ["codex", "qoder"],
            "ts": "2026-07-11T12:01:00Z",
        },
    )
    append_session_event(
        meeting_dir,
        {
            "event": "OwnerInterruptRaised",
            "round": 1,
            "reason": "guest_failure",
            "ts": "2026-07-11T12:02:00Z",
        },
    )
    return state


def test_card_guest_id_rc_mapping():
    assert card_guest_id({"id": "macro-strategist", "source": "builtin"}) == "macro-strategist"
    assert card_guest_id({"id": "my-agent", "source": "custom"}) == "rc-my-agent"
    assert card_guest_id({"id": "auditor-01", "source": "preset"}) == "rc-auditor-01"


def test_meeting_payload_exposes_slot_hitl_fields():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-160000"
        _seed_meeting(meeting_dir)
        payload = CouncilWebService().meeting_payload(meeting_dir)
        assert payload["failure_policy"] == "fail_fast"
        assert "allow_partial" in payload.get("failure_policy_options", [])
        assert payload["guest_slots"]["r001:qoder"]["phase"] == "Skipped"
        assert payload["hitl"]["reason"] == "guest_failure"
        assert payload["owner_required"] is True
        assert "partial_warnings" in payload


def test_council_status_prefers_slot_phase_over_guest_completed():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-161000"
        state = _seed_meeting(meeting_dir)
        append_session_event(
            meeting_dir,
            {
                "event": "guest_completed",
                "round": 1,
                "guest": "qoder",
                "success": True,
                "duration_s": 9.0,
                "ts": "2026-07-11T12:03:00Z",
            },
        )
        statuses = build_council_status(meeting_dir, state, guests={"codex": {}, "qoder": {}})
        by_guest = {s["guest"]: s for s in statuses}
        assert by_guest["codex"]["status"] == "failed"
        assert by_guest["codex"]["phase"] == "Failed"
        assert by_guest["qoder"]["status"] == "skipped"
        assert by_guest["qoder"]["phase"] == "Skipped"
        assert "fail_fast" in by_guest["qoder"]["detail"] or "跳过" in by_guest["qoder"]["detail"]


def test_meeting_payload_partial_warnings():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-162000"
        warnings = [
            {
                "round": 1,
                "failed_guests": ["qoder"],
                "succeeded_guests": ["codex"],
                "ts": "2026-07-11T12:00:00Z",
            }
        ]
        _seed_meeting(
            meeting_dir,
            state_extra={
                "owner_required": False,
                "failure_policy": "allow_partial",
                "partial_warnings": warnings,
                "guest_slots": {},
                "hitl": {"open": False, "reason": "", "round": 0},
            },
        )
        payload = CouncilWebService().meeting_payload(meeting_dir)
        assert payload["partial_warnings"] == warnings
        assert payload["failure_policy"] == "allow_partial"


def test_web_update_runtime_policy():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-163000"
        _seed_meeting(meeting_dir, state_extra={"owner_required": False})
        svc = CouncilWebService()
        with mock.patch.object(svc, "try_current_meeting_dir", return_value=meeting_dir):
            result = svc.update_runtime_policy(
                failure_policy="all_must_succeed",
                require_before_promote=True,
            )
        assert result["ok"] is True
        payload = result["meeting"]
        assert payload["failure_policy"] == "all_must_succeed"
        assert payload["hitl"]["require_before_promote"] is True