"""Hotfix: parallel RESPOND batch append + single index rebuild."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from council.adapters.claim_ledger import append_claim_events_batch, rebuild_index
from council.claims import append_promote_event, verify_index_rebuild_invariant


def test_append_claim_events_batch_rebuilds_once():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
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
        events = [
            {
                "event": "RESPOND",
                "claim_id": "clm-000001",
                "response": "SUPPORT",
                "guest": "qwen",
                "meeting_id": "meet-test",
            },
            {
                "event": "RESPOND",
                "claim_id": "clm-000001",
                "response": "CHALLENGE",
                "guest": "laguna",
                "meeting_id": "meet-test",
            },
        ]
        with mock.patch(
            "council.adapters.claim_ledger._write_claim_index_under_lock",
            wraps=__import__(
                "council.adapters.claim_ledger", fromlist=["_write_claim_index_under_lock"]
            )._write_claim_index_under_lock,
        ) as write_index:
            count = append_claim_events_batch(root, events)
        assert count == 2
        assert write_index.call_count == 1
        verify_index_rebuild_invariant(root)


def test_parallel_runner_uses_batch_not_per_event_rebuild():
    parallel_src = (
        Path(__file__).resolve().parent.parent.parent
        / "apps"
        / "research_council"
        / "lib"
        / "council"
        / "runners"
        / "parallel.py"
    ).read_text(encoding="utf-8")
    assert "append_claim_events_batch" in parallel_src
    assert "rebuild_index(DATA_ROOT)" not in parallel_src