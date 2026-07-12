"""Executor policy — inspect_invoke, strict deny, parallel cap."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

from council.adapters.executor_policy import (
    ExecutorDeniedError,
    InvokeContext,
    inspect_invoke,
    invoke_cli,
)
from council.adapters.meeting_events import meeting_event_log
from council.runners.parallel import process_parallel_guest
from council.selection import max_parallel_from_config
from missionos.context import ContextPack
from missionos.session.events import load_session_events
from missionos.utils import set_relax_cli


def test_inspect_invoke_mock_mode_allows():
    prev = os.environ.get("COUNCIL_MOCK")
    os.environ["COUNCIL_MOCK"] = "1"
    try:
        ctx = InvokeContext(command="", guest="codex", round_num=1, kind="guest")
        assert inspect_invoke(ctx) == "allow"
    finally:
        if prev is None:
            os.environ.pop("COUNCIL_MOCK", None)
        else:
            os.environ["COUNCIL_MOCK"] = prev


def test_inspect_invoke_strict_denies_missing_command():
    set_relax_cli(False)
    try:
        prev = os.environ.pop("COUNCIL_MOCK", None)
        ctx = InvokeContext(
            command="/nonexistent-council-cli-xyz",
            guest="codex",
            round_num=1,
            kind="guest",
        )
        assert inspect_invoke(ctx) == "deny"
        if prev is not None:
            os.environ["COUNCIL_MOCK"] = prev
    finally:
        set_relax_cli(False)


def test_invoke_cli_strict_records_executor_denied():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-170000"
        meeting_dir.mkdir(parents=True)
        (meeting_dir / "errors").mkdir()
        log = meeting_event_log(meeting_dir)
        set_relax_cli(False)
        prev_mock = os.environ.pop("COUNCIL_MOCK", None)
        try:
            try:
                invoke_cli(
                    "/nonexistent-council-cli-xyz",
                    "ping",
                    mock_label="test",
                    round_num=1,
                    guest="codex",
                    kind="guest",
                    timeout_seconds=5,
                    meeting_dir=meeting_dir,
                    event_log=log,
                )
                raise AssertionError("expected ExecutorDeniedError")
            except ExecutorDeniedError as exc:
                assert "unavailable" in exc.reason
        finally:
            set_relax_cli(False)
            if prev_mock is not None:
                os.environ["COUNCIL_MOCK"] = prev_mock

        events = load_session_events(meeting_dir)
        assert any(e.get("event") == "ExecutorDenied" for e in events)
        err_files = list((meeting_dir / "errors").glob("*.md"))
        assert err_files
        assert "ExecutorDenied" in err_files[0].read_text(encoding="utf-8")


def test_parallel_guest_strict_does_not_silent_succeed():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-171000"
        for sub in ("raw", "summaries", "prompts", "errors"):
            (meeting_dir / sub).mkdir(parents=True)
        ContextPack.write(
            meeting_dir / "context",
            body="# Market\n",
            scope="gold",
            topic="t",
            generated_at="2026-07-11T12:00:00Z",
        )
        state = {
            "meeting_id": meeting_dir.name,
            "topic": "t",
            "owner_question": "t",
            "confirmed_points": [],
            "conflicts": [],
            "open_questions": [],
        }
        from council.context.service import MeetingContextService

        snapshot = MeetingContextService(Path(tmp)).snapshot_for_round(meeting_dir, state, round_num=1)
        log = meeting_event_log(meeting_dir)
        set_relax_cli(False)
        prev_mock = os.environ.pop("COUNCIL_MOCK", None)
        try:
            with mock.patch("council.runners.parallel.generate_research_prompt", return_value="# prompt\n"):
                entry = process_parallel_guest(
                    meeting_dir=meeting_dir,
                    state=state,
                    guests={"codex": {"command": "/nonexistent-council-cli-xyz", "timeout_seconds": 30}},
                    guest_name="codex",
                    round_num=1,
                    snapshot=snapshot,
                    event_log=log,
                )
        finally:
            set_relax_cli(False)
            if prev_mock is not None:
                os.environ["COUNCIL_MOCK"] = prev_mock

        assert entry["success"] is False
        assert entry.get("executor_denied") is True
        assert list((meeting_dir / "summaries").glob("*.summary.json")) == []


def test_max_parallel_from_config_guests_alias():
    assert max_parallel_from_config({"max_parallel": 6}) == 6
    assert max_parallel_from_config({"max_parallel_guests": 4}) == 4
    assert max_parallel_from_config({}) == 3
    assert max_parallel_from_config({"max_parallel_guests": 99}) == 8