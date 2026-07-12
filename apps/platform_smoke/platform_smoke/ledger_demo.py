"""Append-only ledger demo using missionos only (no council imports)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from missionos.ledger.store import append_event, load_events
from missionos.utils import utc_now


def run_ledger_demo(data_root: Path, *, message: str = "platform-smoke") -> dict[str, Any]:
    data_root = Path(data_root)
    ledger_path = data_root / "notes.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    event = {"event": "NOTE", "ts": utc_now(), "message": message}
    append_event(ledger_path, event)
    loaded = load_events(ledger_path)
    return {
        "ledger": str(ledger_path),
        "count": len(loaded),
        "last_event": loaded[-1].get("event") if loaded else None,
    }