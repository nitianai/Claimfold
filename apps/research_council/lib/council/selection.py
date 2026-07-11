"""Guest selection and config helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from council.focus_rules import FOCUS_RULES
from council.guest_aliases import GUEST_ALIASES
from missionos.utils import clamp_int


def resolve_guest_alias(name: str, roster: list[str]) -> str | None:
    key = name.strip().lower()
    resolved = GUEST_ALIASES.get(key, key)
    if resolved in roster:
        return resolved
    if key in roster:
        return key
    return None


def load_full_config(config_path: Path) -> dict[str, Any]:
    import yaml

    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def max_parallel_from_config(cfg: dict[str, Any]) -> int:
    return clamp_int(cfg.get("max_parallel", 3), default=3, min_val=1, max_val=8)


def select_guests_for_focus(
    focus: str, roster: list[str], guests: dict[str, Any], explicit: list[str] | None = None
) -> list[str]:
    if explicit:
        out = []
        for name in explicit:
            g = resolve_guest_alias(name, roster)
            if g and g not in out and guests.get(g, {}).get("enabled", True):
                out.append(g)
        if out:
            return out

    text = (focus or "").lower()
    scores: dict[str, int] = {g: 0 for g in roster}
    for keywords, preferred in FOCUS_RULES:
        if any(k.lower() in text for k in keywords):
            for i, g in enumerate(preferred):
                if g in scores:
                    scores[g] += 10 - i

    ranked = sorted(roster, key=lambda g: (-scores[g], roster.index(g)))
    picked = [g for g in ranked if scores[g] > 0][:3]
    if len(picked) < 2:
        picked = roster[: min(3, len(roster))]
    return picked