"""Tests for MeetingContextService and RoundContextSnapshot."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from council.claims import append_promote_event, rebuild_index
from council.context.service import MeetingContextService, RoundContextSnapshot
from council.prompts import build_research_prompt_context
from missionos.context import ContextPack


def _write_market_context(meeting_dir: Path, body: str) -> None:
    ContextPack.write(
        meeting_dir / "context",
        body=body,
        scope="gold,usd",
        topic="macro",
        generated_at="2026-07-11T12:00:00Z",
    )


def test_snapshot_for_round_loads_market_context_and_claims():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_dir = root / "meet-20260711-120000"
        meeting_dir.mkdir(parents=True)
        _write_market_context(meeting_dir, "# Gold\n\nSpot 4100.")

        append_promote_event(
            root,
            {
                "event": "PROMOTE",
                "statement": "黄金短期偏强",
                "scope": {
                    "domain": "finance",
                    "subjects": ["gold"],
                    "valid_from": "2026-07-01",
                    "valid_until": "2026-08-01",
                },
                "evidence_refs": ["raw/round-001-qwen.md"],
            },
        )
        rebuild_index(root)

        state = {
            "meeting_id": meeting_dir.name,
            "topic": "黄金一周走势",
            "current_focus": "黄金、美元",
            "confirmed_points": [],
            "conflicts": [],
            "open_questions": [],
            "guest_summaries": {},
        }

        service = MeetingContextService(root)
        snap = service.snapshot_for_round(meeting_dir, state, round_num=1)

        assert snap.meeting_id == meeting_dir.name
        assert snap.round_num == 1
        assert "Spot 4100" in snap.market_context
        assert len(snap.prior_claims) == 1
        assert snap.prior_claims[0]["claim_id"].startswith("clm-")
        assert "黄金短期偏强" in snap.prior_claims_text


def test_snapshot_state_is_isolated_from_later_mutations():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_dir = root / "meet-20260711-120000"
        meeting_dir.mkdir(parents=True)
        _write_market_context(meeting_dir, "# Context")

        state = {
            "meeting_id": meeting_dir.name,
            "topic": "测试",
            "current_focus": "黄金",
            "confirmed_points": ["A"],
            "conflicts": [],
            "open_questions": [],
            "guest_summaries": {},
        }

        service = MeetingContextService(root)
        snap = service.snapshot_for_round(meeting_dir, state, round_num=2)
        state["confirmed_points"].append("B")

        assert snap.state["confirmed_points"] == ["A"]


def test_build_research_prompt_context_uses_snapshot_without_rereading_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_dir = root / "meet-20260711-120000"
        meeting_dir.mkdir(parents=True)
        _write_market_context(meeting_dir, "# Snapshot body")

        state = {
            "meeting_id": meeting_dir.name,
            "topic": "黄金",
            "current_focus": "黄金",
            "confirmed_points": ["cp1"],
            "conflicts": ["cf1"],
            "open_questions": ["oq1"],
            "guest_summaries": {},
        }
        guests = {"qwen": {"role": "Macro", "role_id": "macro_strategist"}}

        service = MeetingContextService(root)
        snap = service.snapshot_for_round(meeting_dir, state, round_num=1)

        with mock.patch(
            "council.prompts.read_market_context",
            side_effect=AssertionError("should not re-read market context"),
        ), mock.patch(
            "council.prompts.select_claims_for_injection",
            side_effect=AssertionError("should not re-select claims"),
        ):
            ctx = build_research_prompt_context(
                state, guests, "qwen", meeting_dir, snapshot=snap
            )

        assert "Snapshot body" in ctx["market_context"]
        assert ctx["confirmed_points"].startswith("- cp1")


def test_parallel_round_merges_claim_events_on_main_thread_only():
    """Regression: respond_events are buffered per guest, ledger writes happen after pool."""
    parallel_src = (
        Path(__file__).resolve().parent.parent.parent
        / "apps"
        / "research_council"
        / "lib"
        / "council"
        / "runners"
        / "parallel.py"
    ).read_text(encoding="utf-8")
    guest_block = parallel_src.split("def process_parallel_guest", 1)[1].split(
        "def require_parallel_success", 1
    )[0]
    round_block = parallel_src.split("def run_one_parallel_round", 1)[1]

    assert "append_event" not in guest_block
    assert "pending_claim_events" in round_block
    assert "for ev in pending_claim_events" in round_block