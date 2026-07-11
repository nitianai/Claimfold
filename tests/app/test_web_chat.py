"""Web chat feed builder tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from council.web.chat import build_chat_feed
from missionos.context import ContextPack
from missionos.session.events import append_session_event


def test_build_chat_feed_includes_guest_and_system_messages():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-120000"
        for sub in ("raw", "summaries", "prompts"):
            (meeting_dir / sub).mkdir(parents=True)
        ContextPack.write(
            meeting_dir / "context",
            body="# Market\nGold 4100",
            scope="gold",
            topic="macro",
            generated_at="2026-07-11T12:00:00Z",
        )
        append_session_event(
            meeting_dir,
            {
                "event": "round_started",
                "round": 1,
                "guests": ["codex"],
                "ts": "2026-07-11T12:01:00Z",
            },
        )
        (meeting_dir / "raw" / "round-001-codex.md").write_text("判断：黄金偏强", encoding="utf-8")
        (meeting_dir / "summaries" / "round-001-codex.summary.json").write_text(
            json.dumps(
                {
                    "confirmed_points": ["金价4100"],
                    "conflicts": [],
                    "open_questions": [],
                    "guest_position_summary": "偏强",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state = {
            "meeting_id": meeting_dir.name,
            "topic": "黄金",
            "round": 1,
            "owner_views": ["Owner 看好黄金"],
            "next_question": "下周走势？",
            "owner_question": "黄金",
            "history": [
                {
                    "round": 1,
                    "timestamp": "2026-07-11T12:02:00Z",
                    "entries": [
                        {
                            "guest": "codex",
                            "success": True,
                            "raw_output_path": "raw/round-001-codex.md",
                            "summary_json_path": "summaries/round-001-codex.summary.json",
                            "used_mock_guest": False,
                            "duration_s": 12.0,
                        }
                    ],
                }
            ],
        }
        feed = build_chat_feed(meeting_dir, state)
        kinds = {m["kind"] for m in feed}
        assert "guest" in kinds
        assert "system" in kinds
        assert "owner" in kinds
        guest_msg = next(m for m in feed if m["kind"] == "guest")
        assert "黄金偏强" in guest_msg["content"]