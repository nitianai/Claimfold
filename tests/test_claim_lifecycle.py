import json
import tempfile
from pathlib import Path

from claim_lifecycle import (
    append_promote_event,
    load_events,
    parse_claim_responses_from_raw,
    validate_promotion_candidate,
)


def test_append_promote_event_allocates_unique_ids():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        id1 = append_promote_event(
            root,
            {"event": "PROMOTE", "statement": "first", "scope": {"domain": "x", "subjects": ["a"]}},
        )
        id2 = append_promote_event(
            root,
            {"event": "PROMOTE", "statement": "second", "scope": {"domain": "x", "subjects": ["b"]}},
        )
        assert id1 != id2
        events = load_events(root)
        promote_ids = [e["claim_id"] for e in events if e.get("event") == "PROMOTE"]
        assert promote_ids == [id1, id2]


def test_promotion_rejects_open_questions():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260710-120000"
        (meeting_dir / "raw").mkdir(parents=True)
        raw = meeting_dir / "raw" / "round-001-qwen.md"
        raw.write_text("TSLA 收 $406.55，地缘风险上升时黄金倾向上涨", encoding="utf-8")
        state = {"history": [{"mode": "parallel", "guests": ["qwen", "nemo"]}], "conflicts": []}
        errors = validate_promotion_candidate(
            statement="下周方向？",
            evidence_refs=["raw/round-001-qwen.md"],
            meeting_dir=meeting_dir,
            state=state,
            field="open_questions",
            index=0,
        )
        assert any("open_questions" in e for e in errors)


def test_promotion_strips_speaker_prefix_for_json_mode_anchor():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260710-120000"
        (meeting_dir / "raw").mkdir(parents=True)
        evidence_text = "Revenue grew 10% year over year in Q2"
        raw = meeting_dir / "raw" / "round-001-codex.md"
        raw.write_text(
            json.dumps(
                {
                    "speaker": "codex",
                    "evidence": [evidence_text],
                    "position": "bullish",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        state = {"history": [{"mode": "parallel", "guests": ["codex", "qoder"]}], "conflicts": []}
        errors = validate_promotion_candidate(
            statement=f"[codex] {evidence_text}",
            evidence_refs=["raw/round-001-codex.md"],
            meeting_dir=meeting_dir,
            state=state,
            field="confirmed_points",
            index=0,
        )
        assert not any("statement anchor" in e for e in errors)


def test_promotion_accepts_statement_with_spaces_in_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260710-120000"
        (meeting_dir / "raw").mkdir(parents=True)
        statement = "Revenue grew 10% year over year in Q2"
        raw = meeting_dir / "raw" / "round-001-qwen.md"
        raw.write_text(f"Analysis: {statement} per filings.", encoding="utf-8")
        state = {"history": [{"mode": "parallel", "guests": ["qwen", "nemo"]}], "conflicts": []}
        errors = validate_promotion_candidate(
            statement=statement,
            evidence_refs=["raw/round-001-qwen.md"],
            meeting_dir=meeting_dir,
            state=state,
            field="confirmed_points",
            index=0,
        )
        assert not any("statement anchor" in e for e in errors)


def _promotion_errors(*, meeting_dir: Path, evidence_refs: list[str], statement: str) -> list[str]:
    state = {"history": [{"mode": "parallel", "guests": ["qwen", "nemo"]}], "conflicts": []}
    return validate_promotion_candidate(
        statement=statement,
        evidence_refs=evidence_refs,
        meeting_dir=meeting_dir,
        state=state,
        field="confirmed_points",
        index=0,
    )


def test_promotion_rejects_directory_evidence_ref():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260710-120000"
        (meeting_dir / "raw").mkdir(parents=True)
        statement = "Revenue grew 10% year over year in Q2"
        errors = _promotion_errors(
            meeting_dir=meeting_dir,
            evidence_refs=["raw/"],
            statement=statement,
        )
        assert any("必须是文件" in e for e in errors)
        assert not any("IsADirectoryError" in e for e in errors)


def test_promotion_rejects_traversal_evidence_ref():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260710-120000"
        (meeting_dir / "raw").mkdir(parents=True)
        outside = meeting_dir.parent / "outside-secret.txt"
        outside.write_text("Revenue grew 10% year over year in Q2", encoding="utf-8")
        statement = "Revenue grew 10% year over year in Q2"
        errors = _promotion_errors(
            meeting_dir=meeting_dir,
            evidence_refs=["raw/../outside-secret.txt"],
            statement=statement,
        )
        assert any("禁止目录穿越" in e or "越界" in e for e in errors)
        assert not any("statement anchor" in e for e in errors)


def test_promotion_rejects_outside_allowed_evidence_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260710-120000"
        prompts = meeting_dir / "prompts"
        prompts.mkdir(parents=True)
        secret = prompts / "leak.md"
        secret.write_text("Revenue grew 10% year over year in Q2", encoding="utf-8")
        statement = "Revenue grew 10% year over year in Q2"
        errors = _promotion_errors(
            meeting_dir=meeting_dir,
            evidence_refs=["prompts/leak.md"],
            statement=statement,
        )
        assert any("不在允许目录" in e for e in errors)


def test_parse_claim_responses_filters_unknown_ids():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260710-120000"
        meeting_dir.mkdir()
        raw = (
            "claim_responses:\n"
            "claim_id: clm-000099 | response: CHALLENGE | statement: not injected\n"
            "claim_id: clm-000004 | response: CHALLENGE | statement: valid challenge\n"
        )
        events = parse_claim_responses_from_raw(
            raw,
            claim_id="clm-000004",
            guest="mimo",
            meeting_id=meeting_dir.name,
            meeting_dir=meeting_dir,
            allowed_claim_ids={"clm-000004"},
            raw_rel_path=f"{meeting_dir.name}/raw/round-001-mimo.md",
        )
        assert len(events) == 1
        assert events[0]["claim_id"] == "clm-000004"
        assert events[0]["evidence_refs"] == [f"{meeting_dir.name}/raw/round-001-mimo.md"]