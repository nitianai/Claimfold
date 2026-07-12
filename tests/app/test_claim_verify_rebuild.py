"""Claim verify — envelope, index rebuild invariants, export bundle."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from council.adapters.claim_ledger import index_path, rebuild_claim_index
from council.claims import (
    CLAIM_EVENT_SCHEMA_VERSION,
    append_claim_event,
    append_promote_event,
    ensure_claim_envelope,
    verify_index_rebuild_invariant,
    verify_ledger_monotonicity,
    verify_rebuild_roundtrip,
)
from council.adapters.claim_envelope import normalize_schema_version
from missionos.ledger.store import load_events


def test_ensure_claim_envelope_stamps_new_events():
    ev = ensure_claim_envelope({"event": "RETIRE", "claim_id": "clm-000001", "reason": "test"})
    assert ev["schema_version"] == CLAIM_EVENT_SCHEMA_VERSION
    assert ev["ts"]


def test_normalize_schema_version_defaults_to_one():
    assert normalize_schema_version({"event": "PROMOTE"}) == 1
    assert normalize_schema_version({"event": "PROMOTE", "schema_version": 2}) == 2


def test_append_claim_event_writes_schema_version():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        append_claim_event(
            root,
            {
                "event": "RESPOND",
                "claim_id": "clm-000001",
                "response": "SUPPORT",
                "guest": "codex",
            },
        )
        events = load_events(root)
        assert len(events) == 1
        assert events[0]["schema_version"] == CLAIM_EVENT_SCHEMA_VERSION
        assert events[0]["ts"]


def test_verify_rebuild_roundtrip_after_delete_index():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        append_promote_event(
            root,
            {
                "event": "PROMOTE",
                "statement": "黄金偏强",
                "scope": {"domain": "macro", "subjects": ["gold"]},
                "fingerprint": "sha256:abc",
                "evidence_refs": ["raw/x.md"],
            },
        )
        rebuild_claim_index(root)
        ok, errors = verify_rebuild_roundtrip(root)
        assert ok, errors
        assert index_path(root).is_file()


def test_verify_index_rebuild_invariant_detects_stale_index():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cid = append_promote_event(
            root,
            {
                "event": "PROMOTE",
                "statement": "第一条",
                "scope": {"domain": "x", "subjects": ["a"]},
            },
        )
        rebuild_claim_index(root)
        idx = json.loads(index_path(root).read_text(encoding="utf-8"))
        idx["claims"][cid]["status"] = "TAMPERED"
        index_path(root).write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        ok, errors = verify_index_rebuild_invariant(root)
        assert not ok
        assert any("hash" in e or "不一致" in e for e in errors)


def test_verify_ledger_monotonicity_rejects_claim_id_regression():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "claims" / "claims.jsonl"
        ledger.parent.mkdir(parents=True)
        rows = [
            {
                "event": "PROMOTE",
                "claim_id": "clm-000002",
                "statement": "b",
                "ts": "2026-07-12T10:00:00Z",
            },
            {
                "event": "PROMOTE",
                "claim_id": "clm-000001",
                "statement": "a",
                "ts": "2026-07-12T10:01:00Z",
            },
        ]
        ledger.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

        ok, errors = verify_ledger_monotonicity(root)
        assert not ok
        assert any("回退" in e for e in errors)


def test_export_claims_bundle_script():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        append_promote_event(
            root,
            {
                "event": "PROMOTE",
                "statement": "export me",
                "scope": {"domain": "x", "subjects": ["a"]},
            },
        )
        rebuild_claim_index(root)
        env = {**os.environ, "COUNCIL_DATA_ROOT": str(root)}
        script = Path(__file__).resolve().parents[2] / "scripts" / "export_claims_bundle.py"
        proc = subprocess.run(
            [sys.executable, str(script), "-o", str(root / "out")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        bundles = list((root / "out").glob("claims-bundle-*"))
        assert len(bundles) == 1
        manifest = json.loads((bundles[0] / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["schema_version"] == 1
        assert manifest["claim_count"] == 1
        assert (bundles[0] / "claims.jsonl").is_file()
        assert (bundles[0] / "claims_index.json").is_file()