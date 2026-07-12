"""ClaimLedgerAdapter（主张账本适配器）— Claim 投影与 ID 分配，调用 missionos.ledger。"""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from council.adapters.claim_envelope import ensure_claim_envelope
from council.adapters.claim_stream_isolation import assert_claim_ledger_event_type
from missionos.ledger.store import (
    append_event,
    claims_dir,
    ensure_claims_dir,
    ledger_path,
    load_events,
    with_ledger_lock,
)
from missionos.utils import atomic_write_json, utc_now

INDEX_FILE = "claims_index.json"


def index_path(root: Path) -> Path:
    return claims_dir(root) / INDEX_FILE


def normalize_statement(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def canonical_scope(scope: dict[str, Any]) -> str:
    return json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_fingerprint(statement: str, scope: dict[str, Any]) -> str:
    payload = normalize_statement(statement) + "|" + canonical_scope(scope)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def _max_promote_id_from_text(text: str) -> int:
    max_n = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event") != "PROMOTE":
            continue
        m = re.match(r"clm-(\d+)", ev.get("claim_id", ""))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n


def next_claim_id(root: Path) -> str:
    f = with_ledger_lock(root)
    try:
        f.seek(0)
        max_n = _max_promote_id_from_text(f.read())
        return f"clm-{max_n + 1:06d}"
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def append_claim_event(root: Path, event: dict[str, Any]) -> None:
    stamped = ensure_claim_envelope(event)
    assert_claim_ledger_event_type(str(stamped.get("event", "")))
    append_event(root, stamped)


def _events_from_locked_ledger(f) -> list[dict[str, Any]]:
    f.seek(0)
    events: list[dict[str, Any]] = []
    for line in f.read().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _write_claim_index_under_lock(root: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    views = fold_claims(events)
    index = {
        "generated_at": utc_now(),
        "claim_count": len(views),
        "claims": views,
    }
    ensure_claims_dir(root)
    atomic_write_json(index_path(root), index)
    return index


def append_claim_events_batch(root: Path, events: list[dict[str, Any]]) -> int:
    """Append RESPOND/RETIRE events under one flock, then rebuild index once."""
    if not events:
        return 0
    f = with_ledger_lock(root)
    try:
        for event in events:
            stamped = ensure_claim_envelope(event)
            assert_claim_ledger_event_type(str(stamped.get("event", "")))
            f.seek(0, 2)
            f.write(json.dumps(stamped, ensure_ascii=False) + "\n")
        f.flush()
        ledger_events = _events_from_locked_ledger(f)
        _write_claim_index_under_lock(root, ledger_events)
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()
    return len(events)


def append_promote_event(root: Path, event: dict[str, Any]) -> str:
    assert_claim_ledger_event_type(str(event.get("event", "PROMOTE")))
    f = with_ledger_lock(root)
    try:
        f.seek(0)
        max_n = _max_promote_id_from_text(f.read())
        out = ensure_claim_envelope(dict(event))
        out["claim_id"] = out.get("claim_id") or f"clm-{max_n + 1:06d}"
        f.seek(0, 2)
        f.write(json.dumps(out, ensure_ascii=False) + "\n")
        f.flush()
        return out["claim_id"]
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def fold_claims(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    promotes: dict[str, dict[str, Any]] = {}
    for ev in events:
        if ev.get("event") == "PROMOTE" and ev.get("claim_id"):
            promotes[ev["claim_id"]] = dict(ev)

    views: dict[str, dict[str, Any]] = {}
    for claim_id, promo in promotes.items():
        status = "TENTATIVE"
        support_count = 0
        challenge_history: list[dict[str, Any]] = []
        respond_history: list[dict[str, Any]] = []
        last_respond_ts = ""

        for ev in events:
            if ev.get("claim_id") != claim_id:
                continue
            if ev.get("event") == "RETIRE":
                status = "RETIRED"
            elif ev.get("event") == "RESPOND":
                respond_history.append(ev)
                last_respond_ts = ev.get("ts", last_respond_ts)
                if ev.get("response") == "SUPPORT":
                    support_count += 1
                if ev.get("response") == "CHALLENGE":
                    challenge_history.append(ev)
                    if status != "RETIRED":
                        status = "CONTESTED"

        views[claim_id] = {
            "claim_id": claim_id,
            "statement": promo.get("statement", ""),
            "scope": promo.get("scope", {}),
            "fingerprint": promo.get("fingerprint", ""),
            "evidence_refs": promo.get("evidence_refs", []),
            "derived_from_meeting": promo.get("derived_from_meeting", ""),
            "status": status,
            "support_count": support_count,
            "challenge_history": challenge_history,
            "respond_history": respond_history,
            "last_respond_ts": last_respond_ts,
            "promoted_at": promo.get("ts", ""),
        }
    return views


def rebuild_claim_index(root: Path) -> dict[str, Any]:
    events = load_events(root)
    views = fold_claims(events)
    index = {
        "generated_at": utc_now(),
        "claim_count": len(views),
        "claims": views,
    }
    ensure_claims_dir(root)
    index_path(root).write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def load_claim_index(root: Path) -> dict[str, Any]:
    path = index_path(root)
    if not path.exists():
        return rebuild_claim_index(root)
    return json.loads(path.read_text(encoding="utf-8"))


# Backward-compatible aliases (Phase 2 → Phase 4 burn-down)
rebuild_index = rebuild_claim_index
load_index = load_claim_index