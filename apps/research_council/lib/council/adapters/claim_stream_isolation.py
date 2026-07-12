"""Claims ledger vs meeting session event stream isolation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CLAIM_LEDGER_EVENT_NAMES = frozenset({"PROMOTE", "RESPOND", "RETIRE"})


def assert_meeting_event_type(event_type: str) -> None:
    if event_type in CLAIM_LEDGER_EVENT_NAMES:
        raise ValueError(
            f"会议事件流禁止写入主张账本事件名: {event_type} "
            f"(allowed claim events: {', '.join(sorted(CLAIM_LEDGER_EVENT_NAMES))})"
        )


def assert_claim_ledger_event_type(event_type: str) -> None:
    if event_type not in CLAIM_LEDGER_EVENT_NAMES:
        raise ValueError(
            f"主张账本仅允许事件: {', '.join(sorted(CLAIM_LEDGER_EVENT_NAMES))}，收到: {event_type}"
        )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid json: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: event must be object")
        events.append(row)
    return events


def scan_claim_ledger_file(path: Path) -> list[str]:
    errors: list[str] = []
    for line_no, row in enumerate(_load_jsonl(path), start=1):
        event_type = str(row.get("event", "")).strip()
        if not event_type:
            errors.append(f"{path}:{line_no}: missing event")
            continue
        try:
            assert_claim_ledger_event_type(event_type)
        except ValueError as exc:
            errors.append(f"{path}:{line_no}: {exc}")
    return errors


def scan_meeting_events_file(path: Path) -> list[str]:
    errors: list[str] = []
    for line_no, row in enumerate(_load_jsonl(path), start=1):
        event_type = str(row.get("event", "")).strip()
        if not event_type:
            errors.append(f"{path}:{line_no}: missing event")
            continue
        try:
            assert_meeting_event_type(event_type)
        except ValueError as exc:
            errors.append(f"{path}:{line_no}: {exc}")
    return errors