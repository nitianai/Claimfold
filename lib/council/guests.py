"""Guest roster and meeting mode helpers."""
from __future__ import annotations

from typing import Any

import yaml

from council.config import CONFIG_FILE


def load_guests() -> dict[str, Any]:
    if not CONFIG_FILE.is_file():
        raise SystemExit(f"Config not found: {CONFIG_FILE}. Run: ./council.sh init")
    with CONFIG_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    guests = data.get("guests", {})
    if not isinstance(guests, dict) or not guests:
        raise SystemExit(
            f"Guest config is empty or invalid: {CONFIG_FILE}\n"
            "Restore config/guests.yaml from template or backup."
        )
    return guests


EXECUTOR_TO_GUEST: dict[str, str] = {
    "qwen_local": "qwen",
    "claude": "claude_sonnet",
    "grok": "laguna",
    "codex": "codex",
    "qoder": "qoder",
}


def resolve_executor_to_guest(executor_id: str, roster: list[str]) -> str:
    """Map plan executor_id to a guests.yaml roster key for legacy runners."""
    from runtime_ext import resolve_guest_alias

    candidate = EXECUTOR_TO_GUEST.get(executor_id, executor_id)
    resolved = resolve_guest_alias(candidate, roster)
    if resolved:
        return resolved
    if candidate in roster:
        return candidate
    if executor_id in roster:
        return executor_id
    raise ValueError(
        f"executor {executor_id!r} has no enabled guest mapping; "
        f"roster={roster}, known executors={sorted(EXECUTOR_TO_GUEST)}"
    )


def guest_roster(guests: dict[str, Any], *, serial: bool = False) -> list[str]:
    skip = {"summarizer", "reporter"}
    roster: list[str] = []
    for name, cfg in guests.items():
        if name in skip or cfg.get("reporter") or cfg.get("summarizer"):
            continue
        if not cfg.get("enabled", True):
            continue
        if serial and is_script_guest(cfg):
            continue
        roster.append(name)
    return roster


def is_json_mode(state: dict[str, Any]) -> bool:
    return state.get("output_format", "json") == "json"


def is_research_mode(state: dict[str, Any]) -> bool:
    return state.get("output_format") == "research" or state.get("round_mode") == "parallel"


def guest_role_id(guests: dict[str, Any], guest_name: str) -> str:
    return guests.get(guest_name, {}).get("role_id", guest_name)


def is_script_guest(guest_cfg: dict[str, Any]) -> bool:
    return guest_cfg.get("guest_type") == "script"


def is_investment_mode(state: dict[str, Any]) -> bool:
    return state.get("meeting_mode") == "investment"
