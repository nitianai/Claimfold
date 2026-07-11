"""GuestSlot projection and runner integration tests."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from council.slots import (
    begin_guest_slot,
    finalize_guest_slot,
    project_guest_slots,
    repair_guest_slots_from_artifacts,
    slot_key,
)
from council.adapters.meeting_events import meeting_event_log
from council.runners.parallel import process_parallel_guest, run_one_parallel_round
from missionos.context import ContextPack
from missionos.session.events import load_session_events


def _seed_meeting(meeting_dir: Path, *, selected: list[str] | None = None) -> None:
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


def test_slot_key_format():
    assert slot_key(2, "qwen") == "r002:qwen"


def test_project_guest_slots_last_event_wins():
    events = [
        {
            "event": "guest_slot_updated",
            "slot": "r001:codex",
            "round": 1,
            "guest_id": "codex",
            "phase": "Running",
            "attempts": 1,
        },
        {
            "event": "guest_slot_updated",
            "slot": "r001:codex",
            "round": 1,
            "guest_id": "codex",
            "phase": "Succeeded",
            "attempts": 1,
            "artifact": {"raw": "raw/round-001-codex.md"},
        },
    ]
    slots = project_guest_slots(events)
    assert slots["r001:codex"]["phase"] == "Succeeded"
    assert slots["r001:codex"]["artifact"]["raw"] == "raw/round-001-codex.md"


def test_parallel_round_writes_guest_slot_events_and_state():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_dir = root / "meetings" / "meet-20260711-120000"
        _seed_meeting(meeting_dir)

        prev_root = os.environ.get("COUNCIL_DATA_ROOT")
        prev_mock = os.environ.get("COUNCIL_MOCK")
        os.environ["COUNCIL_DATA_ROOT"] = str(root)
        os.environ["COUNCIL_MOCK"] = "1"

        def fake_guest(_cmd, _prompt, **kwargs):
            guest = kwargs.get("guest", "guest")
            return f"# Guest {guest}\n\n判断：mock\n", True

        summary = (
            "## confirmed_points\n- 金价4100\n\n"
            "## conflicts\n- 无\n\n"
            "## open_questions\n- 无\n\n"
            "## guest_position_summary\nmock position\n"
        )
        try:
            with mock.patch("council.runners.parallel.invoke_cli", side_effect=fake_guest), mock.patch(
                "council.runners.parallel.run_summarizer_for_guest",
                return_value=(summary, False),
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

        events = load_session_events(meeting_dir)
        slot_events = [e for e in events if e["event"] == "guest_slot_updated"]
        assert len(slot_events) >= 4
        phases_by_guest = {}
        for ev in slot_events:
            if ev.get("round") != 1:
                continue
            phases_by_guest.setdefault(ev["guest_id"], []).append(ev["phase"])
        assert phases_by_guest["codex"][-1] == "Succeeded"
        assert phases_by_guest["qoder"][-1] == "Succeeded"

        state = json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))
        slots = state.get("guest_slots") or {}
        assert slots["r001:codex"]["phase"] == "Succeeded"
        assert slots["r001:qoder"]["phase"] == "Succeeded"
        assert slots["r001:codex"]["artifact"]["raw"] == "raw/round-001-codex.md"
        assert slots["r001:codex"]["artifact"]["summary_json"] == "summaries/round-001-codex.summary.json"


def test_failed_guest_not_marked_succeeded():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-130000"
        _seed_meeting(meeting_dir, selected=["codex"])
        state = json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))

        prev_root = os.environ.get("COUNCIL_DATA_ROOT")
        prev_mock = os.environ.get("COUNCIL_MOCK")
        os.environ["COUNCIL_DATA_ROOT"] = str(tmp)
        os.environ["COUNCIL_MOCK"] = "1"

        from council.context.service import MeetingContextService

        snapshot = MeetingContextService(Path(tmp)).snapshot_for_round(meeting_dir, state, round_num=1)
        log = meeting_event_log(meeting_dir, state["meeting_id"])

        try:
            with mock.patch(
                "council.runners.parallel.invoke_cli",
                side_effect=RuntimeError("cli exploded"),
            ):
                attempts = begin_guest_slot(log, round_num=1, guest_id="codex")
                entry = process_parallel_guest(
                    meeting_dir=meeting_dir,
                    state=state,
                    guests={"codex": {"command": "", "timeout_seconds": 30}},
                    guest_name="codex",
                    round_num=1,
                    snapshot=snapshot,
                )
                finalize_guest_slot(
                    log,
                    round_num=1,
                    guest_id="codex",
                    entry=entry,
                    attempts=attempts,
                )
        finally:
            if prev_root is None:
                os.environ.pop("COUNCIL_DATA_ROOT", None)
            else:
                os.environ["COUNCIL_DATA_ROOT"] = prev_root
            if prev_mock is None:
                os.environ.pop("COUNCIL_MOCK", None)
            else:
                os.environ["COUNCIL_MOCK"] = prev_mock

        assert entry["success"] is False
        slots = project_guest_slots(load_session_events(meeting_dir))
        assert slots["r001:codex"]["phase"] == "Failed"
        assert "cli exploded" in slots["r001:codex"]["message"]


def test_repair_guest_slots_from_artifacts_without_events():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-140000"
        _seed_meeting(meeting_dir, selected=["codex"])
        state = json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))

        (meeting_dir / "raw" / "round-001-codex.md").write_text("# raw\n", encoding="utf-8")
        (meeting_dir / "summaries" / "round-001-codex.summary.json").write_text(
            '{"guest":"codex"}\n',
            encoding="utf-8",
        )

        slots = repair_guest_slots_from_artifacts(meeting_dir, state)
        assert slots["r001:codex"]["phase"] == "Succeeded"
        assert slots["r001:codex"]["artifact"]["raw"] == "raw/round-001-codex.md"