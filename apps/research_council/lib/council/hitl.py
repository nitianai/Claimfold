"""HITL（Human-in-the-loop）— Owner 中断事件化。"""

from __future__ import annotations

from typing import Any

from council.adapters.meeting_events import MeetingEventLog
from missionos.session.events import load_session_events


def publish_owner_interrupt_raised(
    log: MeetingEventLog,
    *,
    round_num: int,
    reason: str,
) -> None:
    log.append("OwnerInterruptRaised", round=round_num, reason=reason)


def publish_owner_interrupt_resolved(
    log: MeetingEventLog,
    *,
    action: str = "continue",
) -> None:
    log.append("OwnerInterruptResolved", action=action)


def project_hitl_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    open_interrupt = False
    reason = ""
    round_num = 0
    last_resolved_action = ""
    for ev in events:
        if ev.get("event") == "OwnerInterruptRaised":
            open_interrupt = True
            reason = str(ev.get("reason") or "")
            round_num = int(ev.get("round") or 0)
        elif ev.get("event") == "OwnerInterruptResolved":
            open_interrupt = False
            last_resolved_action = str(ev.get("action") or "continue")
    return {
        "open": open_interrupt,
        "reason": reason,
        "round": round_num,
        "last_resolved_action": last_resolved_action,
    }


def apply_hitl_projection(meeting_dir, state: dict[str, Any]) -> dict[str, Any]:
    projected = project_hitl_state(load_session_events(meeting_dir))
    hitl = dict(state.get("hitl") or {})
    hitl.update(projected)
    state["hitl"] = hitl
    return projected


def raise_owner_interrupt(
    log: MeetingEventLog,
    state: dict[str, Any],
    *,
    round_num: int,
    reason: str,
) -> None:
    state["owner_required"] = True
    publish_owner_interrupt_raised(log, round_num=round_num, reason=reason)
    hitl = dict(state.get("hitl") or {})
    hitl.update({"open": True, "reason": reason, "round": round_num})
    state["hitl"] = hitl


def resolve_owner_interrupt(
    log: MeetingEventLog,
    state: dict[str, Any],
    *,
    action: str = "continue",
) -> None:
    state["owner_required"] = False
    publish_owner_interrupt_resolved(log, action=action)
    hitl = dict(state.get("hitl") or {})
    hitl.update({"open": False, "last_resolved_action": action})
    state["hitl"] = hitl