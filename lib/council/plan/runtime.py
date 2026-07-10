"""Plan-aware runtime helpers for legacy runners (PR2 bridge until PR3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from council.guests import resolve_executor_to_guest
from council.plan.reader import load_meeting_plan


def load_state_plan(meeting_dir: Path, state: dict[str, Any]) -> Any | None:
    """Load frozen meeting plan when state references meeting_plan_file."""
    rel = state.get("meeting_plan_file")
    if not rel:
        return None
    return load_meeting_plan(meeting_dir / str(rel))


def build_plan_actor_queue(plan: Any, roster: list[str]) -> list[str]:
    """Ordered guest keys for non-owner stage actors (stage order, actor order)."""
    participants_by_role = {p["role_id"]: p["executor_id"] for p in plan["participants"]}
    queue: list[str] = []
    for stage in plan.get("stages", []):
        if stage.get("owner_gate"):
            continue
        for role_id in stage.get("actor_role_ids", []):
            executor_id = participants_by_role.get(role_id)
            if not executor_id:
                continue
            queue.append(resolve_executor_to_guest(executor_id, roster))
    return queue


def plan_guest_roster(plan: Any, guests: dict[str, Any]) -> list[str]:
    """Unique guest keys bound by the frozen plan (plan SoT for serial runs)."""
    from council.guests import guest_roster

    roster = guest_roster(guests, serial=True)
    ordered: list[str] = []
    seen: set[str] = set()
    for participant in plan["participants"]:
        guest = resolve_executor_to_guest(participant["executor_id"], roster)
        if guest not in seen:
            seen.add(guest)
            ordered.append(guest)
    return ordered


def advance_plan_speaker(state: dict[str, Any]) -> None:
    """Advance next_speaker along the frozen plan actor queue."""
    queue = state.get("plan_actor_queue")
    if not queue:
        return
    idx = int(state.get("plan_actor_index", 0))
    next_idx = (idx + 1) % len(queue)
    state["plan_actor_index"] = next_idx
    state["next_speaker"] = queue[next_idx]