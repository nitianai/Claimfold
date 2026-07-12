"""Claim ledger invariants — index 重建一致性与单调性校验。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from council.adapters.claim_ledger import fold_claims, index_path, rebuild_claim_index
from missionos.ledger.store import load_events


def claims_views_hash(views: dict[str, dict[str, Any]]) -> str:
    payload = json.dumps(views, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_index_rebuild_invariant(root: Path) -> tuple[bool, list[str]]:
    """on-disk index 的 claims 视图须与 fold_claims(events) 一致。"""
    errors: list[str] = []
    idx_path = index_path(root)
    if not idx_path.is_file():
        errors.append("claims_index.json 不存在")
        return False, errors

    on_disk = json.loads(idx_path.read_text(encoding="utf-8"))
    events = load_events(root)
    expected = fold_claims(events)

    disk_views = on_disk.get("claims") or {}
    if on_disk.get("claim_count") != len(expected):
        errors.append(
            f"claim_count 不一致: index={on_disk.get('claim_count')} expected={len(expected)}"
        )

    if claims_views_hash(disk_views) != claims_views_hash(expected):
        errors.append("claims 投影与 fold_claims 不一致（hash mismatch）")
        stale = sorted(set(disk_views) - set(expected))
        missing = sorted(set(expected) - set(disk_views))
        if stale:
            errors.append(f"index 含多余 claim: {', '.join(stale)}")
        if missing:
            errors.append(f"index 缺少 claim: {', '.join(missing)}")

    return len(errors) == 0, errors


def verify_ledger_monotonicity(root: Path) -> tuple[bool, list[str]]:
    """PROMOTE claim_id 不回退；事件 ts 非递减（同秒允许）。"""
    errors: list[str] = []
    events = load_events(root)
    last_ts = ""
    last_promote_num = 0

    for line_no, ev in enumerate(events, start=1):
        ts = str(ev.get("ts") or "")
        if last_ts and ts and ts < last_ts:
            errors.append(f"事件 {line_no}: ts 回退 ({ts} < {last_ts})")
        if ts:
            last_ts = ts

        if ev.get("event") != "PROMOTE":
            continue
        cid = str(ev.get("claim_id") or "")
        match = re.match(r"^clm-(\d+)$", cid)
        if not match:
            errors.append(f"事件 {line_no}: 无效 PROMOTE claim_id {cid!r}")
            continue
        num = int(match.group(1))
        if num < last_promote_num:
            errors.append(f"事件 {line_no}: PROMOTE claim_id 回退 {cid}")
        last_promote_num = max(last_promote_num, num)

    return len(errors) == 0, errors


def verify_rebuild_roundtrip(root: Path) -> tuple[bool, list[str]]:
    """删 index → rebuild → 与 fold 结果一致（供 CI 模拟投影可重建）。"""
    errors: list[str] = []
    idx_path = index_path(root)
    events = load_events(root)
    expected = fold_claims(events)
    expected_hash = claims_views_hash(expected)

    if idx_path.is_file():
        idx_path.unlink()

    rebuilt = rebuild_claim_index(root)
    rebuilt_views = rebuilt.get("claims") or {}
    if rebuilt.get("claim_count") != len(expected):
        errors.append(
            f"rebuild claim_count 不一致: {rebuilt.get('claim_count')} vs {len(expected)}"
        )
    if claims_views_hash(rebuilt_views) != expected_hash:
        errors.append("rebuild 后 claims hash 与 fold_claims 不一致")

    return len(errors) == 0, errors