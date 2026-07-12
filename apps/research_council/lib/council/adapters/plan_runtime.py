"""PlanRuntimeAdapter（计划运行时适配器）— Executor→Guest 映射，留在 App 层。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from council.guests import guest_roster, resolve_executor_to_guest
from council.selection import select_guests_for_focus
from missionos.plan.reader import load_meeting_plan


@dataclass(frozen=True)
class RuntimePlanContext:
    plan: Any | None
    roster: list[str]
    source: str  # "plan" | "legacy"


def load_state_plan(meeting_dir: Path, state: dict[str, Any]) -> Any | None:
    rel = state.get("meeting_plan_file")
    if not rel:
        return None
    return load_meeting_plan(meeting_dir / str(rel))


def resolve_runtime_plan(
    meeting_dir: Path,
    state: dict[str, Any],
    guests: dict[str, Any],
    *,
    serial: bool = False,
) -> RuntimePlanContext:
    plan = load_state_plan(meeting_dir, state)
    if plan is not None:
        roster = plan_guest_roster(plan, guests)
        return RuntimePlanContext(plan=plan, roster=roster, source="plan")
    return RuntimePlanContext(
        plan=None,
        roster=guest_roster(guests, serial=serial),
        source="legacy",
    )


def build_plan_actor_queue(plan: Any, roster: list[str]) -> list[str]:
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
    roster = guest_roster(guests, serial=True)
    ordered: list[str] = []
    seen: set[str] = set()
    for participant in plan["participants"]:
        guest = resolve_executor_to_guest(participant["executor_id"], roster)
        if guest not in seen:
            seen.add(guest)
            ordered.append(guest)
    return ordered


def guests_for_plan_stage(plan: Any, state: dict[str, Any], roster: list[str]) -> list[str]:
    idx = int(state.get("plan_stage_index", 0))
    stages = plan.get("stages") or []
    if idx >= len(stages):
        return []
    stage = stages[idx]
    if stage.get("owner_gate"):
        return []
    participants_by_role = {p["role_id"]: p["executor_id"] for p in plan["participants"]}
    guests: list[str] = []
    for role_id in stage.get("actor_role_ids", []):
        executor_id = participants_by_role.get(role_id)
        if not executor_id:
            continue
        guests.append(resolve_executor_to_guest(executor_id, roster))
    return guests


def plan_stage_pause_reason(plan: Any, state: dict[str, Any]) -> str | None:
    idx = int(state.get("plan_stage_index", 0))
    stages = plan.get("stages") or []
    if idx >= len(stages):
        return None
    stage = stages[idx]
    if stage.get("owner_gate"):
        return stage.get("name", "OWNER APPROVAL")
    return None


def advance_plan_stage_index(state: dict[str, Any]) -> None:
    state["plan_stage_index"] = int(state.get("plan_stage_index", 0)) + 1


def advance_past_owner_gate(state: dict[str, Any], plan: Any) -> None:
    idx = int(state.get("plan_stage_index", 0))
    stages = plan.get("stages") or []
    if idx < len(stages) and stages[idx].get("owner_gate"):
        state["plan_stage_index"] = idx + 1


def resolve_parallel_guests(
    ctx: RuntimePlanContext,
    state: dict[str, Any],
    guests: dict[str, Any],
) -> list[str]:
    explicit = state.get("selected_guests") or []
    if explicit:
        return select_guests_for_focus("", ctx.roster, guests, explicit=explicit)
    if ctx.plan is not None:
        selected = guests_for_plan_stage(ctx.plan, state, ctx.roster)
        if selected:
            return selected
    focus = state.get("current_focus") or state.get("next_question") or state.get("topic", "")
    return select_guests_for_focus(focus, ctx.roster, guests)


def advance_plan_speaker(state: dict[str, Any]) -> None:
    queue = state.get("plan_actor_queue")
    if not queue:
        return
    idx = int(state.get("plan_actor_index", 0))
    next_idx = (idx + 1) % len(queue)
    state["plan_actor_index"] = next_idx
    state["next_speaker"] = queue[next_idx]