"""GuestSlot（嘉宾执行槽）— events.jsonl 为源，meeting_state.guest_slots 为投影。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from council.adapters.meeting_events import MeetingEventLog, meeting_event_log
from council.adapters.session_adapter import artifact_paths_research
from council.formatting import round_tag
from missionos.session.events import load_session_events

GUEST_SLOT_PHASES = frozenset({"Pending", "Running", "Succeeded", "Failed", "Skipped"})
DEFAULT_MAX_RETRIES = 1


def slot_key(round_num: int, guest_id: str) -> str:
    return f"r{round_num:03d}:{guest_id}"


def _artifact_from_entry(entry: dict[str, Any]) -> dict[str, str]:
    artifact: dict[str, str] = {}
    for field, key in (
        ("prompt_path", "prompt"),
        ("raw_output_path", "raw"),
        ("summary_json_path", "summary_json"),
        ("summary_md_path", "summary_md"),
        ("error_path", "error"),
    ):
        value = str(entry.get(field, "") or "").strip()
        if value:
            artifact[key] = value
    return artifact


def count_running_attempts(events: list[dict[str, Any]], key: str) -> int:
    return sum(
        1
        for ev in events
        if ev.get("event") == "guest_slot_updated"
        and ev.get("slot") == key
        and ev.get("phase") == "Running"
    )


def publish_guest_slot_updated(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest_id: str,
    phase: str,
    attempts: int = 1,
    max_retries: int = DEFAULT_MAX_RETRIES,
    message: str = "",
    artifact: dict[str, str] | None = None,
) -> None:
    if phase not in GUEST_SLOT_PHASES:
        raise ValueError(f"invalid guest slot phase: {phase}")
    key = slot_key(round_num, guest_id)
    payload: dict[str, Any] = {
        "slot": key,
        "round": round_num,
        "guest_id": guest_id,
        "phase": phase,
        "attempts": attempts,
        "max_retries": max_retries,
        "message": message,
    }
    if artifact:
        payload["artifact"] = artifact
    log.append("guest_slot_updated", **payload)


def begin_guest_slot(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest_id: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> int:
    key = slot_key(round_num, guest_id)
    attempts = count_running_attempts(log.load(), key) + 1
    publish_guest_slot_updated(
        log,
        round_num=round_num,
        guest_id=guest_id,
        phase="Running",
        attempts=attempts,
        max_retries=max_retries,
    )
    return attempts


def skip_guest_slot(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest_id: str,
    reason: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> None:
    publish_guest_slot_updated(
        log,
        round_num=round_num,
        guest_id=guest_id,
        phase="Skipped",
        attempts=0,
        max_retries=max_retries,
        message=reason,
    )


def finalize_guest_slot(
    log: MeetingEventLog,
    *,
    round_num: int,
    guest_id: str,
    entry: dict[str, Any],
    attempts: int,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> None:
    if entry.get("success"):
        publish_guest_slot_updated(
            log,
            round_num=round_num,
            guest_id=guest_id,
            phase="Succeeded",
            attempts=attempts,
            max_retries=max_retries,
            artifact=_artifact_from_entry(entry),
        )
        return

    message = str(entry.get("error") or entry.get("parse_error") or "guest failed")
    phase = "Failed"
    if attempts < max_retries:
        phase = "Pending"
    publish_guest_slot_updated(
        log,
        round_num=round_num,
        guest_id=guest_id,
        phase=phase,
        attempts=attempts,
        max_retries=max_retries,
        message=message,
        artifact=_artifact_from_entry(entry),
    )


def project_guest_slots(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    slots: dict[str, dict[str, Any]] = {}
    for ev in events:
        if ev.get("event") != "guest_slot_updated":
            continue
        key = str(ev.get("slot") or slot_key(int(ev.get("round") or 0), str(ev.get("guest_id") or "")))
        slots[key] = {
            "round": ev.get("round"),
            "guest_id": ev.get("guest_id"),
            "phase": ev.get("phase"),
            "attempts": ev.get("attempts", 1),
            "max_retries": ev.get("max_retries", DEFAULT_MAX_RETRIES),
            "message": ev.get("message", ""),
            "artifact": dict(ev.get("artifact") or {}),
        }
    return slots


def apply_guest_slots_projection(meeting_dir: Path, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    events = load_session_events(meeting_dir)
    projected = project_guest_slots(events)
    if projected:
        state["guest_slots"] = projected
    else:
        state.setdefault("guest_slots", {})
    return projected


def repair_guest_slots_from_artifacts(meeting_dir: Path, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """从 events 投影；若无 slot 事件则按 raw/summary 制品回填终态。"""
    projected = apply_guest_slots_projection(meeting_dir, state)
    if projected:
        return projected

    slots: dict[str, dict[str, Any]] = {}
    raw_dir = meeting_dir / "raw"
    if not raw_dir.is_dir():
        state["guest_slots"] = slots
        return slots

    for raw_path in sorted(raw_dir.glob("round-*-*.md")):
        stem = raw_path.stem
        if not stem.startswith("round-"):
            continue
        body = stem[len("round-") :]
        if "-" not in body:
            continue
        tag, guest_id = body.rsplit("-", 1)
        try:
            round_num = int(tag)
        except ValueError:
            continue

        paths = artifact_paths_research(meeting_dir, round_num, guest_id, round_tag)
        key = slot_key(round_num, guest_id)
        has_summary = paths["summary_json"].is_file()
        has_error = paths["error"].is_file()
        if has_summary:
            phase = "Succeeded"
            message = ""
        elif has_error:
            phase = "Failed"
            message = paths["error"].read_text(encoding="utf-8")[:200]
        else:
            phase = "Pending"
            message = ""

        artifact = {
            "prompt": str(paths["prompt"].relative_to(meeting_dir)) if paths["prompt"].is_file() else "",
            "raw": str(raw_path.relative_to(meeting_dir)),
            "summary_json": (
                str(paths["summary_json"].relative_to(meeting_dir)) if has_summary else ""
            ),
        }
        artifact = {k: v for k, v in artifact.items() if v}
        slots[key] = {
            "round": round_num,
            "guest_id": guest_id,
            "phase": phase,
            "attempts": 1,
            "max_retries": DEFAULT_MAX_RETRIES,
            "message": message,
            "artifact": artifact,
        }

    state["guest_slots"] = slots
    return slots


def format_guest_slots_summary(slots: dict[str, dict[str, Any]]) -> str:
    if not slots:
        return "(无 guest_slots)"
    lines: list[str] = []
    for key in sorted(slots):
        slot = slots[key]
        phase = slot.get("phase", "?")
        attempts = slot.get("attempts", 1)
        guest_id = slot.get("guest_id", "?")
        round_num = slot.get("round", "?")
        artifact = slot.get("artifact") or {}
        raw_ref = artifact.get("raw", "")
        message = str(slot.get("message") or "").strip()
        line = f"  {key}  round={round_num} guest={guest_id}  {phase}  attempts={attempts}"
        if raw_ref:
            line += f"  raw={raw_ref}"
        if message and phase in {"Failed", "Pending"}:
            line += f"  msg={message[:80]}"
        lines.append(line)
    return "\n".join(lines)


def meeting_event_log_for_dir(meeting_dir: Path, state: dict[str, Any]) -> MeetingEventLog:
    return meeting_event_log(meeting_dir, state.get("meeting_id", meeting_dir.name))