"""Build chat-room message feed from meeting artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from council.guests import load_guests_for_meeting
from council.slots import slot_key
from council.interactive.state import is_interactive_mode
from council.web.voice import extract_guest_voice
from missionos.session.events import load_session_events

_EVENT_LABELS = {
    "meeting_started": "会议已开始",
    "context_written": "共享上下文已更新",
    "round_started": "新一轮讨论开始",
    "guest_completed": "嘉宾发言完成",
    "claim_responded": "主张回应已记录",
    "state_merged": "会议状态已合并",
    "session_started": "交互会话开始",
    "floor_granted": "授权发言",
    "floor_requested": "话轮申请",
    "floor_yielded": "话轮让出",
    "message_proposed": "发言提议",
    "message_committed": "发言已记录",
    "context_observed": "上下文已同步",
    "session_paused": "会话暂停",
    "session_ended": "交互会话结束",
    "interrupt_requested": "打断申请",
    "guest_slot_updated": "嘉宾槽状态更新",
    "OwnerInterruptRaised": "需主持人介入",
    "OwnerInterruptResolved": "主持人已放行",
    "ExecutorDenied": "执行器被拒绝",
}


def _guest_label(guests: dict[str, Any], guest_id: str) -> str:
    cfg = guests.get(guest_id, {})
    role = cfg.get("role", "")
    if role:
        return f"{guest_id} · {role}"
    return guest_id


def _read_text(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _messages_from_events(meeting_dir: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for idx, ev in enumerate(load_session_events(meeting_dir)):
        event_type = ev.get("event", "")
        label = _EVENT_LABELS.get(event_type, event_type or "系统")
        detail_parts: list[str] = []
        if event_type == "round_started":
            guests = ev.get("guests") or []
            detail_parts.append(f"嘉宾: {', '.join(guests)}")
        elif event_type == "context_written":
            detail_parts.append(f"范围: {ev.get('scope', '')}")
        elif event_type == "guest_completed":
            guest = ev.get("guest", "")
            if ev.get("success"):
                detail_parts.append(
                    f"{guest} · {ev.get('duration_s', '?')}s · "
                    f"+cp:{ev.get('confirmed_points_added', 0)} "
                    f"+cf:{ev.get('conflicts_added', 0)}"
                )
            else:
                detail_parts.append(f"{guest} 失败: {ev.get('error', '')[:120]}")
        elif event_type == "state_merged":
            detail_parts.append(
                f"Round {ev.get('round')} · {ev.get('duration_s', '?')}s · "
                f"+cp:{ev.get('confirmed_points_added', 0)}"
            )
        elif event_type == "session_started":
            detail_parts.append(f"嘉宾: {', '.join(ev.get('guests') or [])}")
        elif event_type in ("floor_granted", "floor_yielded", "message_committed"):
            detail_parts.append(
                f"{ev.get('guest', '')} · Turn {ev.get('turn', '?')}"
                + (f" · reply_to {ev.get('reply_to')}" if ev.get("reply_to") else "")
            )
        elif event_type == "floor_requested":
            detail_parts.append(
                f"{ev.get('guest', '')} · urgency {ev.get('urgency', 0)}"
                + (f" · build_on {ev.get('build_on')}" if ev.get("build_on") else "")
            )
        elif event_type == "session_paused":
            remaining = ev.get("remaining_queue") or []
            if remaining:
                detail_parts.append(f"待发言: {', '.join(remaining)}")
        elif event_type == "session_ended":
            detail_parts.append(
                f"Round {ev.get('round')} · {ev.get('guest_count', 0)} 位嘉宾 · "
                f"{ev.get('duration_s', '?')}s"
            )
        content = label
        if detail_parts:
            content += "\n" + "\n".join(detail_parts)
        messages.append(
            {
                "id": f"event-{idx}",
                "kind": "system",
                "author": "system",
                "author_label": "系统",
                "round": ev.get("round"),
                "content": content,
                "timestamp": ev.get("ts", ""),
            }
        )
    return messages


def _messages_from_history(
    meeting_dir: Path,
    state: dict[str, Any],
    guests: dict[str, Any],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for block in state.get("history", []):
        round_num = block.get("round")
        ts = block.get("timestamp", "")
        for entry in block.get("entries", []):
            guest = entry.get("guest", "guest")
            raw_rel = entry.get("raw_output_path", "")
            raw_path = meeting_dir / raw_rel if raw_rel else None
            raw_body = _read_text(raw_path) if raw_path else ""
            summary = entry.get("summary_data") or {}
            if raw_body:
                content = extract_guest_voice(raw_body)
            else:
                content = summary.get("guest_position_summary", "") or "(无发言内容)"
            if not content.strip():
                content = summary.get("guest_position_summary", "") or "(无发言内容)"
            messages.append(
                {
                    "id": f"round-{round_num}-{guest}",
                    "kind": "guest",
                    "author": guest,
                    "author_label": _guest_label(guests, guest),
                    "round": round_num,
                    "content": content,
                    "timestamp": ts,
                    "success": entry.get("success", True),
                    "used_mock": entry.get("used_mock_guest", False),
                    "duration_s": entry.get("duration_s"),
                }
            )
    return messages


def _messages_from_owner(state: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for idx, view in enumerate(state.get("owner_views", [])):
        messages.append(
            {
                "id": f"owner-view-{idx}",
                "kind": "owner",
                "author": "owner",
                "author_label": "你 · 观点",
                "round": state.get("round"),
                "content": view,
                "timestamp": "",
            }
        )
    question = state.get("next_question") or state.get("owner_question") or ""
    topic = state.get("topic", "")
    if question and question != topic:
        messages.append(
            {
                "id": "owner-question",
                "kind": "owner",
                "author": "owner",
                "author_label": "你 · 当前问题",
                "round": state.get("round"),
                "content": question,
                "timestamp": "",
            }
        )
    return messages


def _load_summary_data(meeting_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    summary = entry.get("summary_data")
    if isinstance(summary, dict) and summary:
        return summary
    summary_rel = entry.get("summary_json_path", "")
    if not summary_rel:
        return {}
    summary_path = meeting_dir / summary_rel
    if not summary_path.is_file():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build_guest_positions(
    meeting_dir: Path,
    state: dict[str, Any],
    guests: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Per-guest position cards for inspector (not chat stream)."""
    guests = guests or load_guests_for_meeting(meeting_dir)
    positions: list[dict[str, Any]] = []
    for block in state.get("history", []):
        round_num = block.get("round")
        for entry in block.get("entries", []):
            if not entry.get("success", True):
                continue
            guest = entry.get("guest", "guest")
            data = _load_summary_data(meeting_dir, entry)
            positions.append(
                {
                    "guest": guest,
                    "guest_label": _guest_label(guests, guest),
                    "round": round_num,
                    "position": data.get("guest_position_summary", "").strip(),
                    "confirmed": (data.get("confirmed_points") or [])[:2],
                    "conflicts": (data.get("conflicts") or [])[:2],
                    "open_questions": (data.get("open_questions") or [])[:2],
                    "used_mock": bool(entry.get("used_mock_guest")),
                    "duration_s": entry.get("duration_s"),
                }
            )
    return positions


_SLOT_PHASE_TO_STATUS = {
    "Succeeded": "done",
    "Running": "running",
    "Failed": "failed",
    "Skipped": "skipped",
    "Pending": "idle",
}


def _detail_from_slot(slot: dict[str, Any]) -> str:
    phase = str(slot.get("phase") or "")
    if phase == "Succeeded":
        attempts = slot.get("attempts", 1)
        return f"完成 · 尝试 {attempts}"
    if phase == "Failed":
        return str(slot.get("message") or "失败")[:80]
    if phase == "Skipped":
        return str(slot.get("message") or "已跳过")[:80]
    if phase == "Running":
        return "发言中…"
    if phase == "Pending":
        return "等待执行"
    return "待命"


def _slots_for_round(state: dict[str, Any], round_num: int) -> dict[str, dict[str, Any]]:
    by_guest: dict[str, dict[str, Any]] = {}
    for key, slot in (state.get("guest_slots") or {}).items():
        if int(slot.get("round") or 0) != round_num:
            continue
        guest_id = str(slot.get("guest_id") or "")
        if not guest_id and ":" in key:
            guest_id = key.split(":", 1)[1]
        if guest_id:
            by_guest[guest_id] = {**slot, "slot": key}
    return by_guest


def build_council_status(
    meeting_dir: Path,
    state: dict[str, Any],
    guests: dict[str, Any] | None = None,
    *,
    task: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Per-guest run status — guest_slots phase 优先，guest_completed 回退。"""
    guests = guests or load_guests_for_meeting(meeting_dir)
    selected = list(state.get("selected_guests") or [])
    current_round = int(state.get("round") or 0)
    task = task or {}
    task_running = bool(task.get("running"))
    task_name = str(task.get("task") or "")

    round_guests: list[str] = []
    completed: dict[str, dict[str, Any]] = {}
    for ev in load_session_events(meeting_dir):
        if ev.get("event") in ("round_started", "session_started") and int(ev.get("round") or 0) == current_round:
            round_guests = list(ev.get("guests") or round_guests)
        if ev.get("event") == "guest_completed" and int(ev.get("round") or 0) == current_round:
            guest = str(ev.get("guest", ""))
            if guest:
                completed[guest] = ev
        if ev.get("event") == "message_committed" and int(ev.get("round") or 0) == current_round:
            guest = str(ev.get("guest", ""))
            if guest:
                completed[guest] = ev

    slot_by_guest = _slots_for_round(state, current_round)
    slot_guests = list(slot_by_guest.keys())
    roster = selected or round_guests or slot_guests
    current_speaker = state.get("current_speaker")
    speaking_queue = list(state.get("speaking_queue") or [])
    interactive_active = is_interactive_mode(state) and state.get("session_status") in ("active", "paused")

    statuses: list[dict[str, Any]] = []
    for gid in roster:
        phase = ""
        status = "idle"
        detail = "待命"
        slot = slot_by_guest.get(gid)
        if slot:
            phase = str(slot.get("phase") or "")
            status = _SLOT_PHASE_TO_STATUS.get(phase, "idle")
            detail = _detail_from_slot(slot)
        elif gid in completed:
            ev = completed[gid]
            status = "done" if ev.get("success", True) else "failed"
            detail = f"{ev.get('duration_s', '?')}s"
            if not ev.get("success"):
                detail = str(ev.get("error", "失败"))[:80]
        elif task_running and task_name == "run_interactive" and interactive_active and current_speaker == gid:
            status = "running"
            detail = "发言中…"
        elif task_running and task_name == "run_interactive" and gid in speaking_queue:
            status = "queued"
            detail = "排队中"
        elif task_running and task_name == "run_parallel" and gid in round_guests and gid not in completed:
            status = "running"
            detail = "发言中…"
        elif task_running and task_name == "context":
            status = "idle"
            detail = "等待上下文"
        else:
            status = "idle"
            detail = "待命"

        statuses.append(
            {
                "guest": gid,
                "guest_label": _guest_label(guests, gid),
                "status": status,
                "phase": phase or None,
                "detail": detail,
                "round": current_round,
                "attempts": slot.get("attempts") if slot else None,
                "slot": slot.get("slot") if slot else slot_key(current_round, gid) if current_round else None,
            }
        )
    return statuses


def build_chat_feed(meeting_dir: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    guests = load_guests_for_meeting(meeting_dir)
    feed: list[dict[str, Any]] = []
    feed.extend(_messages_from_events(meeting_dir))
    feed.extend(_messages_from_history(meeting_dir, state, guests))
    feed.extend(_messages_from_owner(state))

    def sort_key(msg: dict[str, Any]) -> tuple:
        ts = msg.get("timestamp") or ""
        round_num = msg.get("round") or 0
        kind_order = {"system": 0, "guest": 1, "owner": 2}.get(msg.get("kind", ""), 1)
        return (ts, round_num, kind_order, msg.get("id", ""))

    feed.sort(key=sort_key)
    return feed