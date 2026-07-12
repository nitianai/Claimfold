"""Claim ledger event envelope — schema_version + ts 默认值。"""

from __future__ import annotations

from typing import Any

from missionos.utils import utc_now

CLAIM_EVENT_SCHEMA_VERSION = 1


def ensure_claim_envelope(event: dict[str, Any]) -> dict[str, Any]:
    """为新写入事件补齐 envelope；缺省 schema_version 视为 1。"""
    out = dict(event)
    event_type = str(out.get("event") or "").strip()
    if not event_type:
        raise ValueError("claim event missing event field")
    if not out.get("schema_version"):
        out["schema_version"] = CLAIM_EVENT_SCHEMA_VERSION
    if not out.get("ts"):
        out["ts"] = utc_now()
    return out


def normalize_schema_version(event: dict[str, Any]) -> int:
    raw = event.get("schema_version")
    if raw is None or raw == "":
        return CLAIM_EVENT_SCHEMA_VERSION
    try:
        return int(raw)
    except (TypeError, ValueError):
        return CLAIM_EVENT_SCHEMA_VERSION