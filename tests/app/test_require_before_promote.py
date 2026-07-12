"""PR-C.2 — require_before_promote blocks claim promote during owner gate."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from unittest import mock

from council.commands.claims import cmd_claim_promote
from council.failure_policy import validate_promote_hitl_gate


def _seed_meeting(meeting_dir: Path, *, owner_required: bool, require_gate: bool) -> None:
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "raw").mkdir()
    state = {
        "confirmed_points": ["黄金在地缘风险下倾向上涨"],
        "conflicts": [],
        "open_questions": [],
        "owner_required": owner_required,
        "hitl": {
            "every_n_rounds": 3,
            "require_before_promote": require_gate,
            "open": owner_required,
            "reason": "every_n_rounds",
            "round": 2,
        },
        "history": [{"mode": "parallel", "guests": ["qwen"]}],
    }
    (meeting_dir / "meeting_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (meeting_dir / "raw" / "round-001-qwen.md").write_text("分析：黄金偏强", encoding="utf-8")


def _promote_args(meeting_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        from_state="confirmed_points[0]",
        meeting=meeting_dir.name,
        evidence=["raw/round-001-qwen.md"],
        owner_override=False,
        domain="macro",
        subjects="gold",
        regime_tags="risk-off",
        valid_from="2026-07-01",
        valid_until="2026-08-01",
        conditions="地缘风险",
    )


def test_validate_promote_hitl_gate_blocks_when_owner_required():
    state = {
        "owner_required": True,
        "hitl": {"require_before_promote": True, "reason": "guest_failure"},
    }
    errors = validate_promote_hitl_gate(state)
    assert errors
    assert "continue" in errors[0]


def test_validate_promote_hitl_gate_allows_when_gate_disabled():
    state = {
        "owner_required": True,
        "hitl": {"require_before_promote": False},
    }
    assert validate_promote_hitl_gate(state) == []


def test_cmd_promote_rejects_when_require_before_promote_and_owner_pause():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_dir = root / "meet-20260712-150000"
        _seed_meeting(meeting_dir, owner_required=True, require_gate=True)
        with mock.patch("council.commands.claims.DATA_ROOT", root), mock.patch(
            "council.commands.claims.MEETINGS_DIR", root
        ):
            try:
                cmd_claim_promote(_promote_args(meeting_dir))
                raise AssertionError("expected SystemExit")
            except SystemExit as exc:
                assert "Owner 闸门" in str(exc)
                assert "晋升拒绝" in str(exc)