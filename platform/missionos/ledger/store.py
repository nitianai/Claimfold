"""Append-only JSONL ledger store with exclusive flock."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

CLAIMS_DIR_NAME = "claims"
LEDGER_FILE = "claims.jsonl"


def claims_dir(root: Path) -> Path:
    return root / CLAIMS_DIR_NAME


def ledger_path(root: Path) -> Path:
    return claims_dir(root) / LEDGER_FILE


def ensure_claims_dir(root: Path) -> Path:
    d = claims_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    ledger = ledger_path(root)
    if not ledger.exists():
        ledger.write_text("", encoding="utf-8")
    return d


def load_events(root: Path) -> list[dict[str, Any]]:
    path = ledger_path(root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def append_event(root: Path, event: dict[str, Any]) -> None:
    ensure_claims_dir(root)
    with ledger_path(root).open("a", encoding="utf-8") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def with_ledger_lock(root: Path):
    """Open ledger for read+append under an exclusive flock."""
    ensure_claims_dir(root)
    path = ledger_path(root)
    f = path.open("a+", encoding="utf-8")
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    return f