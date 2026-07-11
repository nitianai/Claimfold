"""CLI promotion gates — mock / evidence / raw anchor / owner_override."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from unittest import mock

from council.commands.claims import cmd_claim_promote
from council.claims import load_events, validate_promotion_candidate


def _seed_meeting(meeting_dir: Path, *, confirmed: list[str]) -> None:
    meeting_dir.mkdir(parents=True)
    (meeting_dir / "raw").mkdir()
    (meeting_dir / "summaries").mkdir()
    state = {
        "confirmed_points": confirmed,
        "conflicts": [],
        "open_questions": [],
        "history": [{"mode": "parallel", "guests": ["qwen", "nemo"]}],
    }
    (meeting_dir / "meeting_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _promote_args(
    meeting_dir: Path,
    *,
    evidence: list[str] | None = None,
    owner_override: bool = False,
    index: int = 0,
) -> argparse.Namespace:
    return argparse.Namespace(
        from_state=f"confirmed_points[{index}]",
        meeting=meeting_dir.name,
        evidence=evidence or [],
        owner_override=owner_override,
        domain="macro",
        subjects="gold",
        regime_tags="risk-off",
        valid_from="",
        valid_until="",
        conditions="地缘风险上升",
    )


def test_cmd_promote_rejects_mock_statement():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-120000"
        _seed_meeting(meeting_dir, confirmed=["[MOCK] 黄金看涨"])
        raw = meeting_dir / "raw" / "round-001-qwen.md"
        raw.write_text("[MOCK] 黄金看涨", encoding="utf-8")
        try:
            cmd_claim_promote(_promote_args(meeting_dir, evidence=["raw/round-001-qwen.md"]))
            raise AssertionError("expected SystemExit")
        except SystemExit:
            pass


def test_cmd_promote_rejects_missing_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-120000"
        _seed_meeting(meeting_dir, confirmed=["黄金在地缘风险下倾向上涨"])
        try:
            cmd_claim_promote(_promote_args(meeting_dir, evidence=[]))
            raise AssertionError("expected SystemExit")
        except SystemExit:
            pass


def test_cmd_promote_rejects_summary_only_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-120000"
        statement = "黄金在地缘风险下倾向上涨"
        _seed_meeting(meeting_dir, confirmed=[statement])
        summary = meeting_dir / "summaries" / "round-001-qwen.json"
        summary.write_text(json.dumps({"position": statement}, ensure_ascii=False), encoding="utf-8")
        errors = validate_promotion_candidate(
            statement=statement,
            evidence_refs=["summaries/round-001-qwen.json"],
            meeting_dir=meeting_dir,
            state=json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8")),
            field="confirmed_points",
            index=0,
        )
        assert any("raw/" in e for e in errors)
        try:
            cmd_claim_promote(
                _promote_args(meeting_dir, evidence=["summaries/round-001-qwen.json"])
            )
            raise AssertionError("expected SystemExit")
        except SystemExit:
            pass


def test_cmd_promote_succeeds_with_raw_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_dir = root / "meet-20260711-120000"
        statement = "黄金在地缘风险下倾向上涨"
        _seed_meeting(meeting_dir, confirmed=[statement])
        raw = meeting_dir / "raw" / "round-001-qwen.md"
        raw.write_text(f"分析：{statement}", encoding="utf-8")
        with mock.patch("council.commands.claims.DATA_ROOT", root), mock.patch(
            "council.commands.claims.MEETINGS_DIR", root
        ), mock.patch("council.commands.claims.CLAIMS_DIR", root / "claims"):
            cmd_claim_promote(
                _promote_args(meeting_dir, evidence=["raw/round-001-qwen.md"])
            )
        events = load_events(root)
        assert any(e.get("event") == "PROMOTE" for e in events)


def test_cmd_promote_owner_override_records_audit_note():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_dir = root / "meet-20260711-120000"
        _seed_meeting(meeting_dir, confirmed=["[MOCK] 黄金看涨"])
        raw = meeting_dir / "raw" / "round-001-qwen.md"
        raw.write_text("[MOCK] 黄金看涨", encoding="utf-8")
        with mock.patch("council.commands.claims.DATA_ROOT", root), mock.patch(
            "council.commands.claims.MEETINGS_DIR", root
        ), mock.patch("council.commands.claims.CLAIMS_DIR", root / "claims"):
            cmd_claim_promote(
                _promote_args(
                    meeting_dir,
                    evidence=["raw/round-001-qwen.md"],
                    owner_override=True,
                )
            )
        events = load_events(root)
        promote = [e for e in events if e.get("event") == "PROMOTE"][-1]
        assert promote.get("promoted_by") == "owner_override"
        assert promote.get("override_note")