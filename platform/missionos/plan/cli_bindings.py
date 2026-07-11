"""Parse ``--bind role=executor`` CLI arguments."""

from __future__ import annotations


def parse_cli_bindings(bind_args: list[str] | None) -> dict[str, str]:
    """Parse repeatable ``role=executor`` bindings; reject duplicates and bad syntax."""
    if not bind_args:
        return {}
    seen: set[str] = set()
    out: dict[str, str] = {}
    for raw in bind_args:
        text = raw.strip()
        if "=" not in text:
            raise ValueError(f"invalid --bind (expected role=executor): {raw!r}")
        role, _, executor = text.partition("=")
        role = role.strip()
        executor = executor.strip()
        if not role or not executor:
            raise ValueError(f"invalid --bind (empty role or executor): {raw!r}")
        if role in seen:
            raise ValueError(f"duplicate --bind for role: {role}")
        seen.add(role)
        out[role] = executor
    return out