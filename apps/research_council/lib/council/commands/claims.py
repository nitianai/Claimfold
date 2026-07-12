"""Council: commands/claims."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from council.claims import (
    append_claim_event,
    append_promote_event,
    compute_fingerprint,
    load_index,
    rebuild_index,
    validate_promotion_candidate,
    validate_scope,
    verify_index_rebuild_invariant,
    verify_ledger_monotonicity,
    verify_three_meeting_chain,
)
from missionos.utils import resolve_meeting_path, utc_now

from council.config import CLAIMS_DIR, DATA_ROOT, MEETINGS_DIR
from council.state_store import get_current_meeting_dir, load_state



def parse_from_state_ref(ref: str) -> tuple[str, int]:
    m = re.match(r"^(confirmed_points|conflicts|open_questions)\[(\d+)\]$", ref.strip())
    if not m:
        raise SystemExit(f"Invalid --from-state: {ref} (expected e.g. conflicts[0])")
    return m.group(1), int(m.group(2))


def resolve_meeting_dir(meeting_id: str | None) -> Path:
    if meeting_id:
        meeting_dir = resolve_meeting_path(MEETINGS_DIR, meeting_id.strip())
        if not meeting_dir.exists():
            raise SystemExit(f"Meeting not found: {meeting_dir}")
        return meeting_dir
    return get_current_meeting_dir()


def build_scope_from_args(args: argparse.Namespace) -> dict[str, Any]:
    subjects = [s.strip() for s in (args.subjects or "").split(",") if s.strip()]
    regime_tags = [s.strip() for s in (args.regime_tags or "").split(",") if s.strip()]
    conditions = [s.strip() for s in (args.conditions or "").split(";") if s.strip()]
    return {
        "domain": (args.domain or "").strip(),
        "subjects": subjects,
        "regime_tags": regime_tags,
        "valid_from": (args.valid_from or "").strip(),
        "valid_until": (args.valid_until or "").strip(),
        "conditions": conditions,
        "exclusions": [],
    }


def cmd_claim_promote(args: argparse.Namespace) -> None:
    field, index = parse_from_state_ref(args.from_state)
    meeting_dir = resolve_meeting_dir(args.meeting)
    state = load_state(meeting_dir)
    scope = build_scope_from_args(args)

    scope_errors = validate_scope(scope)
    if scope_errors:
        raise SystemExit("scope 校验失败:\n  - " + "\n  - ".join(scope_errors))

    items = state.get(field, [])
    if index >= len(items):
        raise SystemExit(f"{field}[{index}] 不存在（共 {len(items)} 条）")
    statement = str(items[index]).strip()

    evidence_refs = [e.strip() for e in (args.evidence or []) if e.strip()]
    promo_errors = validate_promotion_candidate(
        statement=statement,
        evidence_refs=evidence_refs,
        meeting_dir=meeting_dir,
        state=state,
        field=field,
        index=index,
    )
    if promo_errors and not args.owner_override:
        raise SystemExit("晋升拒绝:\n  - " + "\n  - ".join(promo_errors))

    fingerprint = compute_fingerprint(statement, scope)
    event: dict[str, Any] = {
        "event": "PROMOTE",
        "fingerprint": fingerprint,
        "statement": statement,
        "scope": scope,
        "epistemic_status": "TENTATIVE",
        "evidence_refs": evidence_refs,
        "derived_from_meeting": meeting_dir.name,
        "derived_from_state_ref": f"{field}[{index}]",
        "promoted_by": "owner_override" if args.owner_override else "owner",
        "ts": utc_now(),
    }
    if args.owner_override and promo_errors:
        event["override_note"] = "; ".join(promo_errors)

    claim_id = append_promote_event(DATA_ROOT, event)
    index_data = rebuild_index(DATA_ROOT)
    print(f"Promoted {claim_id} → TENTATIVE")
    print(f"Statement: {statement[:120]}{'...' if len(statement) > 120 else ''}")
    print(f"Ledger: {CLAIMS_DIR / 'claims.jsonl'}")
    print(f"Index claims: {index_data.get('claim_count', 0)}")


def cmd_claim_retire(args: argparse.Namespace) -> None:
    claim_id = args.claim_id.strip()
    if not re.match(r"^clm-\d+$", claim_id):
        raise SystemExit(f"Invalid claim_id: {claim_id}")

    index = load_index(DATA_ROOT)
    if claim_id not in index.get("claims", {}):
        raise SystemExit(f"Unknown claim: {claim_id}")

    event = {
        "event": "RETIRE",
        "claim_id": claim_id,
        "reason": (args.reason or "owner decision").strip(),
        "actor": "owner",
        "ts": utc_now(),
    }
    append_claim_event(DATA_ROOT, event)
    index_data = rebuild_index(DATA_ROOT)
    view = index_data.get("claims", {}).get(claim_id, {})
    print(f"Retired {claim_id} → {view.get('status', 'RETIRED')}")
    print(f"Reason: {event['reason']}")


def cmd_claim_rebuild_index(_: argparse.Namespace) -> None:
    index_data = rebuild_index(DATA_ROOT)
    print(f"Rebuilt claims_index.json — {index_data.get('claim_count', 0)} claims")
    print(f"Path: {CLAIMS_DIR / 'claims_index.json'}")


def cmd_claim_list(_: argparse.Namespace) -> None:
    index = load_index(DATA_ROOT)
    claims = index.get("claims", {})
    if not claims:
        print("(无主张)")
        return
    for cid in sorted(claims.keys()):
        view = claims[cid]
        stmt = view.get("statement", "")
        short = stmt[:80] + ("..." if len(stmt) > 80 else "")
        print(f"{cid} [{view.get('status', '?')}] {short}")


def cmd_claim_verify(_: argparse.Namespace) -> None:
    checks = [
        ("三场会议链", verify_three_meeting_chain(DATA_ROOT)),
        ("index 重建不变量", verify_index_rebuild_invariant(DATA_ROOT)),
        ("账本单调性", verify_ledger_monotonicity(DATA_ROOT)),
    ]
    errors: list[str] = []
    passed: list[str] = []
    for label, (ok, errs) in checks:
        if ok:
            passed.append(label)
        else:
            errors.extend(f"[{label}] {e}" for e in errs)

    if errors:
        print("✗ Claim verify 失败:")
        for err in errors:
            print(f"  - {err}")
        raise SystemExit(1)

    print("✓ Claim verify 通过")
    for label in passed:
        print(f"  · {label}")
    index = load_index(DATA_ROOT)
    for cid, view in sorted(index.get("claims", {}).items()):
        print(f"  {cid}: {view.get('status')} (support={view.get('support_count', 0)})")


def cmd_claim(args: argparse.Namespace) -> None:
    handlers = {
        "promote": cmd_claim_promote,
        "retire": cmd_claim_retire,
        "rebuild-index": cmd_claim_rebuild_index,
        "list": cmd_claim_list,
        "verify": cmd_claim_verify,
    }
    handler = handlers.get(args.claim_cmd)
    if not handler:
        raise SystemExit(f"Unknown claim subcommand: {args.claim_cmd}")
    handler(args)

