"""Load Executor→Guest mapping from config/bindings/."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_MAP_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "bindings" / "executor-guest.yaml"


@lru_cache(maxsize=1)
def load_executor_guest_map() -> dict[str, str]:
    if not _MAP_FILE.is_file():
        raise SystemExit(f"Executor-guest mapping missing: {_MAP_FILE}")
    with _MAP_FILE.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    raw = data.get("mappings", data)
    if not isinstance(raw, dict) or not raw:
        raise SystemExit(f"Executor-guest mapping invalid or empty: {_MAP_FILE}")
    return {str(k).strip(): str(v).strip() for k, v in raw.items()}


EXECUTOR_TO_GUEST: dict[str, str] = load_executor_guest_map()