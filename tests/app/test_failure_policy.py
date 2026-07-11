"""FailurePolicy + HITL event tests."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from council.commands.meeting_owner import cmd_continue
from council.runners.parallel import run_one_parallel_round
from missionos.context import ContextPack
from missionos.session.events import load_session_events


def _seed_meeting(
    meeting_dir: Path,
    *,
    selected: list[str] | None = None,
    failure_policy: str = "allow_partial",
) -> None:
    meeting_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("raw", "summaries", "prompts", "errors"):
        (meeting_dir / sub).mkdir(exist_ok=True)
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
        "failure_policy": failure_policy,
        "partial_warnings": [],
        "hitl": {"every_n_rounds": 3, "require_before_promote": False},
    }
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


def _summary_body() -> str:
    return (
        "## confirmed_points\n- 金价4100\n\n"
        "## conflicts\n- 无\n\n"
        "## open_questions\n- 无\n\n"
        "## guest_position_summary\nmock position\n"
    )


def _run_parallel_with_guest_mock(
    meeting_dir: Path,
    *,
    guest_side_effect,
) -> dict:
    root = meeting_dir.parent.parent
    prev_root = os.environ.get("COUNCIL_DATA_ROOT")
    prev_mock = os.environ.get("COUNCIL_MOCK")
    os.environ["COUNCIL_DATA_ROOT"] = str(root)
    os.environ["COUNCIL_MOCK"] = "1"
    try:
        with mock.patch("council.runners.parallel.invoke_cli", side_effect=guest_side_effect), mock.patch(
            "council.runners.parallel.run_summarizer_for_guest",
            return_value=(_summary_body(), False),
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
    return json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))


def test_allow_partial_records_warning_on_mixed_results():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meetings" / "meet-20260711-150000"
        _seed_meeting(meeting_dir, failure_policy="allow_partial")

        calls: list[str] = []

        def guest_side_effect(_cmd, _prompt, **kwargs):
            guest = kwargs.get("guest", "guest")
            calls.append(guest)
            if guest == "codex":
                return f"# Guest {guest}\n\n判断：mock\n", True
            raise RuntimeError("qoder failed")

        state = _run_parallel_with_guest_mock(meeting_dir, guest_side_effect=guest_side_effect)
        assert state["round"] == 1
        assert state["owner_required"] is False
        assert len(state["partial_warnings"]) == 1
        assert state["partial_warnings"][0]["failed_guests"] == ["qoder"]
        assert state["partial_warnings"][0]["succeeded_guests"] == ["codex"]


def test_all_must_succeed_raises_owner_interrupt_on_failure():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meetings" / "meet-20260711-151000"
        _seed_meeting(meeting_dir, failure_policy="all_must_succeed")

        def guest_side_effect(_cmd, _prompt, **kwargs):
            guest = kwargs.get("guest", "guest")
            if guest == "codex":
                return f"# Guest {guest}\n\n判断：mock\n", True
            raise RuntimeError("qoder failed")

        state = _run_parallel_with_guest_mock(meeting_dir, guest_side_effect=guest_side_effect)
        assert state["owner_required"] is True
        events = load_session_events(meeting_dir)
        raised = [e for e in events if e["event"] == "OwnerInterruptRaised"]
        assert raised
        assert raised[-1]["reason"] == "guest_failure"


def test_fail_fast_skips_remaining_guests():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meetings" / "meet-20260711-152000"
        _seed_meeting(meeting_dir, failure_policy="fail_fast")

        calls: list[str] = []

        def guest_side_effect(_cmd, _prompt, **kwargs):
            guest = kwargs.get("guest", "guest")
            calls.append(guest)
            if guest == "codex":
                raise RuntimeError("codex failed first")
            return f"# Guest {guest}\n\n判断：mock\n", True

        _run_parallel_with_guest_mock(meeting_dir, guest_side_effect=guest_side_effect)
        assert calls == ["codex"]
        slots = json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))["guest_slots"]
        assert slots["r001:codex"]["phase"] == "Failed"
        assert slots["r001:qoder"]["phase"] == "Skipped"


def test_continue_writes_owner_interrupt_resolved():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_dir = root / "meetings" / "meet-20260711-153000"
        _seed_meeting(meeting_dir)
        state_path = meeting_dir / "meeting_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["owner_required"] = True
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with mock.patch(
            "council.commands.meeting_owner.get_current_meeting_dir",
            return_value=meeting_dir,
        ):
            cmd_continue(argparse_namespace())

        events = load_session_events(meeting_dir)
        resolved = [e for e in events if e["event"] == "OwnerInterruptResolved"]
        assert resolved
        assert resolved[-1]["action"] == "continue"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["owner_required"] is False


class argparse_namespace:
    pass