"""Generic event replay interface — projection logic supplied by App."""

from __future__ import annotations

from typing import Any, Callable


def replay(
    events: list[dict[str, Any]],
    projector: Callable[[Any, dict[str, Any]], Any],
    *,
    initial: Any = None,
) -> Any:
    """Fold events through an App-supplied projector."""
    state = initial
    for event in events:
        state = projector(state, event)
    return state