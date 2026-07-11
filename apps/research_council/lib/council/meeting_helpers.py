"""Council: meeting_helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from missionos.utils import utc_now

from council.formatting import format_guest_summaries, format_list, round_tag


def ensure_no_overwrite(path: Path) -> None:
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing artifact: {path}")


def write_summary_file(
    path: Path,
    *,
    meeting_id: str,
    round_num: int,
    guest: str,
    body: str,
) -> None:
    raw_rel = f"../raw/round-{round_tag(round_num)}-{guest}.md"
    frontmatter = (
        "---\n"
        f"meeting_id: {meeting_id}\n"
        f"round: {round_num}\n"
        f"guest: {guest}\n"
        f"source: {raw_rel}\n"
        "summary_type: compressed\n"
        "---\n\n"
    )
    path.write_text(frontmatter + body.strip() + "\n", encoding="utf-8")


def state_digest(state: dict[str, Any]) -> str:
    parts = [
        state.get("topic", ""),
        state.get("owner_question", ""),
        format_list(state.get("confirmed_points", [])),
        format_list(state.get("conflicts", [])),
        format_list(state.get("open_questions", [])),
        format_guest_summaries(state.get("guest_summaries", {})),
        format_list(state.get("owner_views", [])),
    ]
    return "\n".join(parts)


def stop_suggestions(state: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    if state.get("stop_recommendation"):
        suggestions.append(state["stop_recommendation"])
    history = state.get("history", [])
    if len(history) >= 2:
        last_two = history[-2:]
        for label, idx in (("confirmed_points", 0), ("conflicts", 1), ("open_questions", 2)):
            if all(history_additions(h)[idx] == 0 for h in last_two):
                suggestions.append(f"连续两轮没有新增 {label}")

    if len(state.get("open_questions", [])) > 5:
        suggestions.append("open_questions 超过 5 个，议题可能发散")

    if len(state_digest(state)) > 1500:
        suggestions.append("meeting_state 摘要超过 1500 字")

    if len(history) >= 2:
        last_guests = [h.get("guest") for h in history[-2:]]
        if last_guests[0] == last_guests[1]:
            suggestions.append("连续两轮同一 Guest 发言，可能重复")

    return suggestions


def owner_pause_message(state: dict[str, Any] | None = None) -> str:
    n = 3
    if state:
        n = state.get("max_round_before_owner", 3)
    return (
        f"\n⏸  Owner 接管 required（已完成 {n} 轮）\n"
        "请选择：\n"
        "  ./council.sh continue        # 继续最多 3 轮\n"
        "  ./council.sh stop            # 停止并生成 final.md\n"
        "  ./council.sh view \"观点\"     # 注入 Owner 观点\n"
        "  ./council.sh ask \"新问题\"    # 更新当前问题\n"
    )


def history_additions(entry: dict[str, Any]) -> tuple[int, int, int]:
    if entry.get("mode") == "parallel":
        return (
            entry.get("confirmed_points_added", 0),
            entry.get("conflicts_added", 0),
            entry.get("open_questions_added", 0),
        )
    return (
        entry.get("confirmed_points_added", entry.get("items_added", 0)),
        entry.get("conflicts_added", 0),
        entry.get("open_questions_added", 0),
    )


def update_stop_recommendation(state: dict[str, Any]) -> None:
    history = state.get("history", [])
    if len(history) < 2:
        state["stop_recommendation"] = ""
        return
    last_two = history[-2:]
    stale = all(
        history_additions(h)[0] == 0 and history_additions(h)[1] == 0 and history_additions(h)[2] == 0
        for h in last_two
    )
    state["stop_recommendation"] = (
        "连续 2 轮无新增 confirmed/conflict/question，建议停止" if stale else ""
    )


def write_error_file(path: Path, *, guest: str, round_num: int, error: str) -> None:
    body = (
        f"# Guest Error — round {round_tag(round_num)} / {guest}\n\n"
        f"**Time:** {utc_now()}\n\n"
        f"## Error\n\n{error.strip()}\n"
    )
    path.write_text(body, encoding="utf-8")

