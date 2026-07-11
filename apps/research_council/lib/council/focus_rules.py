"""Load Focus Rules（焦点规则）from config — breaks runtime_ext hardcoding."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_RULES_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "focus_rules.yaml"


@lru_cache(maxsize=1)
def load_focus_rules() -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    if not _RULES_FILE.is_file():
        raise SystemExit(f"Focus rules config missing: {_RULES_FILE}")
    with _RULES_FILE.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    raw = data.get("rules", [])
    if not isinstance(raw, list) or not raw:
        raise SystemExit(f"Focus rules invalid or empty: {_RULES_FILE}")
    out: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for entry in raw:
        keywords = entry.get("keywords", [])
        preferred = entry.get("preferred", [])
        if not keywords or not preferred:
            raise SystemExit(f"Focus rule entry missing keywords/preferred: {_RULES_FILE}")
        out.append((tuple(str(k) for k in keywords), tuple(str(p) for p in preferred)))
    return out


FOCUS_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = load_focus_rules()