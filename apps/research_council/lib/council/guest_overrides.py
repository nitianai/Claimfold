"""Per-meeting guest config overrides (session-scoped, does not mutate guests.yaml)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from missionos.utils import atomic_write_json

OVERRIDES_FILENAME = "guest_overrides.json"
_OVERRIDABLE_KEYS = (
    "role",
    "role_id",
    "model",
    "command",
    "executor_id",
    "enabled",
    "allow_parallel",
    "timeout_seconds",
    "model_tier",
    "guest_type",
)


def overrides_path(meeting_dir: Path) -> Path:
    return meeting_dir / OVERRIDES_FILENAME


def load_overrides(meeting_dir: Path) -> dict[str, Any]:
    path = overrides_path(meeting_dir)
    if not path.is_file():
        return {"version": "1.0", "guests": {}, "invited": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": "1.0", "guests": {}, "invited": []}
    data.setdefault("version", "1.0")
    data.setdefault("guests", {})
    data.setdefault("invited", [])
    return data


def save_overrides(meeting_dir: Path, data: dict[str, Any]) -> None:
    payload = {
        "version": "1.0",
        "guests": data.get("guests") or {},
        "invited": data.get("invited") or [],
        "setup": data.get("setup") or {},
    }
    atomic_write_json(overrides_path(meeting_dir), payload)


def merge_guest_config(base_guests: dict[str, Any], meeting_dir: Path | None) -> dict[str, Any]:
    if meeting_dir is None:
        return base_guests
    overrides = load_overrides(meeting_dir)
    guest_overrides = overrides.get("guests") or {}
    if not guest_overrides:
        return base_guests
    merged = copy.deepcopy(base_guests)
    for guest_id, patch in guest_overrides.items():
        if not isinstance(patch, dict):
            continue
        if guest_id in merged:
            entry = dict(merged[guest_id])
            for key in _OVERRIDABLE_KEYS:
                if key in patch and patch[key] is not None:
                    entry[key] = patch[key]
            merged[guest_id] = entry
            continue
        base_key = str(patch.get("base_guest") or "")
        if base_key and base_key in merged:
            entry = dict(merged[base_key])
        else:
            entry = {
                "guest_type": "llm",
                "enabled": True,
                "allow_parallel": True,
                "timeout_seconds": 180,
            }
        for key in _OVERRIDABLE_KEYS:
            if key in patch and patch[key] is not None:
                entry[key] = patch[key]
        entry["enabled"] = patch.get("enabled", entry.get("enabled", True))
        merged[guest_id] = entry
    return merged