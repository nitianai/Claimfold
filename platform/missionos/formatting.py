"""Minimal formatting helpers (no domain vocabulary)."""

from __future__ import annotations

from pathlib import Path


def format_list(items: list[str], empty: str = "(无)") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def render_template(template_path: Path, variables: dict[str, str]) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def round_tag(n: int) -> str:
    return f"{n:03d}"