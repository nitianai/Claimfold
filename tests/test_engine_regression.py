"""P1 regression tests from audit consensus meeting."""

import engine
from claim_lifecycle import parse_claim_responses_from_raw
from utils import atomic_write_json


def test_merge_guest_json_filters_mock_evidence():
    state = {
        "positions": {},
        "confirmed_points": [],
        "conflicts": [],
        "open_questions": [],
        "verifications": [],
        "challenges": [],
        "round_records": [],
        "guest_summaries": {},
    }
    data = {
        "speaker": "mimo",
        "role": "equity",
        "round": 1,
        "position": "neutral",
        "evidence": ["[MOCK/test]", "TSLA $406.55"],
        "risks": ["forced-mock risk"],
        "need_verification": ["待复核 CPI"],
        "challenge_to": "",
        "challenge_question": "",
    }
    counts = engine.merge_guest_json_into_state(state, data)
    assert len(state["confirmed_points"]) == 1
    assert "TSLA" in state["confirmed_points"][0]
    assert counts["items_added"] >= 1


def test_parallel_round_aborts_when_all_fail():
    from council.runners.parallel import require_parallel_success

    entries = [
        {"guest": "a", "success": False},
        {"guest": "b", "success": False},
    ]
    try:
        require_parallel_success(entries, quiet=True)
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert exc.code == 1


def test_claim_respond_evidence_is_precise_raw_path():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260710-120000"
        meeting_dir.mkdir()
        raw_rel = f"{meeting_dir.name}/raw/round-001-codex.md"
        events = parse_claim_responses_from_raw(
            "claim_id: clm-000004 | response: CHALLENGE | statement: test anchor",
            claim_id="clm-000004",
            guest="codex",
            meeting_id=meeting_dir.name,
            meeting_dir=meeting_dir,
            allowed_claim_ids={"clm-000004"},
            raw_rel_path=raw_rel,
        )
        assert len(events) == 1
        assert events[0]["evidence_refs"] == [raw_rel]


def test_atomic_write_survives_read():
    import json
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "state.json"
        atomic_write_json(target, {"round": 1, "status": "running"})
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["round"] == 1