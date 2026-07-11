"""Interactive session runner tests."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from council.interactive.prompts import append_prior_turns, format_prior_turns
from council.interactive.state import ensure_interactive_fields, is_interactive_mode
from council.runners.interactive import run_interactive_turn, run_one_interactive_round
from missionos.context import ContextPack
from missionos.session.events import load_session_events


def _seed_interactive_meeting(meeting_dir: Path, *, selected: list[str] | None = None) -> None:
    meeting_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("raw", "summaries", "prompts", "errors"):
        (meeting_dir / sub).mkdir(exist_ok=True)
    state = {
        "meeting_id": meeting_dir.name,
        "topic": "黄金一周走势",
        "owner_question": "黄金一周走势",
        "meeting_mode": "interactive",
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
        "next_speaker": "codex",
        "next_question": "黄金一周走势",
        "history": [],
        "stop_reason": "",
        "output_format": "research",
        "round_mode": "interactive",
        "selected_guests": selected or ["codex", "qoder"],
        "current_focus": "黄金、美元",
        "stop_recommendation": "",
        "positions": {},
        "challenges": [],
        "verifications": [],
        "round_records": [],
    }
    ensure_interactive_fields(state)
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


def test_is_interactive_mode():
    assert is_interactive_mode({"meeting_mode": "interactive"})
    assert not is_interactive_mode({"meeting_mode": "research"})
    research = {"meeting_mode": "research"}
    ensure_interactive_fields(research)
    assert not is_interactive_mode(research)


def test_format_prior_turns():
    block = format_prior_turns(
        [{"guest": "codex", "turn": 1, "excerpt": "黄金偏强", "reply_to": None}]
    )
    assert "Turn 1" in block
    assert "codex" in block
    assert "黄金偏强" in block


def test_append_prior_turns_adds_section():
    out = append_prior_turns("# Base\n", [{"guest": "grok", "turn": 1, "excerpt": "看多"}])
    assert "本轮已发言" in out
    assert "看多" in out


def test_run_interactive_round_emits_session_events():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-140000"
        _seed_interactive_meeting(meeting_dir, selected=["codex", "qoder"])
        os.environ["COUNCIL_MOCK"] = "1"
        try:
            with mock.patch("council.runners.interactive.DATA_ROOT", Path(tmp)):
                with mock.patch("council.runners.interactive.MeetingContextService") as mcs:
                    from council.context.service import RoundContextSnapshot

                    mcs.return_value.snapshot_for_round.return_value = RoundContextSnapshot(
                        meeting_id=meeting_dir.name,
                        round_num=1,
                        state={"topic": "黄金一周走势", "next_question": "黄金一周走势"},
                        market_context="# Market",
                        prior_claims=(),
                        prior_claims_text="",
                    )
                    run_one_interactive_round(meeting_dir, quiet=True)
        finally:
            os.environ.pop("COUNCIL_MOCK", None)

        events = load_session_events(meeting_dir)
        types = [e["event"] for e in events]
        assert "session_started" in types
        assert "floor_granted" in types
        assert "message_committed" in types
        assert "floor_yielded" in types
        assert "session_ended" in types
        assert "message_proposed" in types
        assert "context_observed" in types

        state = json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))
        assert state["round"] == 1
        assert state["session_status"] == "idle"
        assert len(state["history"]) == 1
        assert state["history"][0]["mode"] == "interactive"

        # Second guest prompt should include first guest prior turn
        prompt_qoder = meeting_dir / "prompts" / "round-001-qoder.prompt.md"
        assert prompt_qoder.is_file()
        body = prompt_qoder.read_text(encoding="utf-8")
        assert "本轮已发言" in body


def test_session_step_pauses_mid_round():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-140100"
        _seed_interactive_meeting(meeting_dir, selected=["codex", "qoder"])
        os.environ["COUNCIL_MOCK"] = "1"
        try:
            with mock.patch("council.runners.interactive.DATA_ROOT", Path(tmp)):
                with mock.patch("council.runners.interactive.MeetingContextService") as mcs:
                    from council.context.service import RoundContextSnapshot

                    mcs.return_value.snapshot_for_round.return_value = RoundContextSnapshot(
                        meeting_id=meeting_dir.name,
                        round_num=1,
                        state={"topic": "黄金一周走势", "next_question": "黄金一周走势"},
                        market_context="# Market",
                        prior_claims=(),
                        prior_claims_text="",
                    )
                    _, finalized = run_interactive_turn(meeting_dir, quiet=True)
        finally:
            os.environ.pop("COUNCIL_MOCK", None)

        assert not finalized
        state = json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))
        assert state["session_status"] == "paused"
        assert state["speaking_queue"] == ["qoder"]
        assert state["round"] == 0