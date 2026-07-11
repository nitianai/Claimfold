"""Interactive prompt augmentation — prior turns within a macro round."""

from __future__ import annotations

from typing import Any


def format_prior_turns(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    lines: list[str] = []
    for msg in messages:
        guest = msg.get("guest", "guest")
        turn = msg.get("turn", "?")
        reply = msg.get("reply_to")
        reply_note = f"（reply_to: {reply}）" if reply else ""
        excerpt = (msg.get("excerpt") or msg.get("content") or "（无摘要）").strip()
        lines.append(f"### Turn {turn} · {guest}{reply_note}\n{excerpt}")
    return "\n\n".join(lines)


def append_prior_turns(prompt: str, messages: list[dict[str, Any]]) -> str:
    block = format_prior_turns(messages)
    if not block:
        return prompt
    return (
        prompt.rstrip()
        + "\n\n## 本轮已发言（请回应或承接，勿重复）\n\n"
        + block
        + "\n"
    )