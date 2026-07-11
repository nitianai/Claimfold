"""Load Guest Alias（嘉宾别名）from config — breaks config ↔ runtime_ext cycle."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ALIASES_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "guest_aliases.yaml"


@lru_cache(maxsize=1)
def load_guest_aliases() -> dict[str, str]:
    if not _ALIASES_FILE.is_file():
        raise SystemExit(f"Guest aliases config missing: {_ALIASES_FILE}")
    with _ALIASES_FILE.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    raw = data.get("aliases", data)
    if not isinstance(raw, dict) or not raw:
        raise SystemExit(f"Guest aliases invalid or empty: {_ALIASES_FILE}")
    return {str(k).strip().lower(): str(v).strip() for k, v in raw.items()}


# Module-level dict for LEGACY_GUEST_MAP spread in config.py
GUEST_ALIASES: dict[str, str] = load_guest_aliases()