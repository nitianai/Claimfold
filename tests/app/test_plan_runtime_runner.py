"""PR3: plan-driven runner resolves guests from meeting_plan.json."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from council.adapters.plan_runtime import (
    advance_past_owner_gate,
    advance_plan_stage_index,
    guests_for_plan_stage,
    plan_stage_pause_reason,
    resolve_parallel_guests,
    resolve_runtime_plan,
)
from council.guests import load_guests
from council.plan import load_meeting_plan
from council.state_store import save_state

GOLDEN_PLAN = (
    Path(__file__).resolve().parent.parent / "fixtures" / "golden" / "project-development.meeting_plan.json"
)


def _guests():
    return load_guests()


def test_resolve_runtime_plan_prefers_frozen_plan():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-plan"
        meeting_dir.mkdir()
        plan = json.loads(GOLDEN_PLAN.read_text(encoding="utf-8"))
        (meeting_dir / "meeting_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        state = {
            "meeting_plan_file": "meeting_plan.json",
            "plan_stage_index": 0,
        }
        guests = _guests()
        ctx = resolve_runtime_plan(meeting_dir, state, guests)
        assert ctx.source == "plan"
        assert ctx.plan is not None
        assert len(ctx.roster) >= 4


def test_guests_for_plan_stage_review_has_two_actors():
    from council.adapters.plan_runtime import plan_guest_roster

    plan = load_meeting_plan(GOLDEN_PLAN)
    guests = _guests()
    roster = plan_guest_roster(plan, guests)
    state = {"plan_stage_index": 2}
    selected = guests_for_plan_stage(plan, state, roster)
    assert len(selected) == 2


def test_resolve_parallel_guests_from_plan_without_explicit_select():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-plan"
        meeting_dir.mkdir()
        plan = json.loads(GOLDEN_PLAN.read_text(encoding="utf-8"))
        (meeting_dir / "meeting_plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        state = {
            "meeting_plan_file": "meeting_plan.json",
            "plan_stage_index": 0,
            "selected_guests": [],
            "topic": "smoke",
        }
        guests = _guests()
        ctx = resolve_runtime_plan(meeting_dir, state, guests)
        selected = resolve_parallel_guests(ctx, state, guests)
        assert len(selected) == 1


def test_owner_gate_pause_and_continue_advances_stage():
    plan = load_meeting_plan(GOLDEN_PLAN)
    state = {"plan_stage_index": 3}
    reason = plan_stage_pause_reason(plan, state)
    assert reason == "OWNER APPROVAL"
    advance_past_owner_gate(state, plan)
    assert state["plan_stage_index"] == 4
    assert guests_for_plan_stage(plan, state, ["codex", "qwen", "qoder"]) != []


def test_serial_runner_reads_plan_from_state_file():
    serial_src = (
        Path(__file__).resolve().parent.parent.parent
        / "apps"
        / "research_council"
        / "lib"
        / "council"
        / "runners"
        / "serial.py"
    ).read_text(encoding="utf-8")
    assert "resolve_runtime_plan" in serial_src


def test_plan_stage_advances_after_parallel_round():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-plan"
        meeting_dir.mkdir()
        state = {"plan_stage_index": 1, "meeting_id": meeting_dir.name, "topic": "t", "history": []}
        save_state(meeting_dir, state)
        advance_plan_stage_index(state)
        assert state["plan_stage_index"] == 2