"""Meeting state persistence."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from council.adapters.session_adapter import get_current_meeting_dir
from council.config import LEGACY_GUEST_MAP
from council.formatting import round_tag
from council.parsers import (
    apply_parsed_summary,
    filter_semantic_items,
    parse_summary_sections,
)
from missionos.session.store import load_json_state, save_json_state


def load_state(meeting_dir: Path) -> dict[str, Any]:
    return load_json_state(meeting_dir)


def save_state(meeting_dir: Path, state: dict[str, Any]) -> None:
    save_json_state(meeting_dir, state)


def rebuild_state_from_summaries(state: dict[str, Any], meeting_dir: Path) -> None:
    last_question = state.get("owner_question", "")
    state["confirmed_points"] = []
    state["conflicts"] = []
    state["open_questions"] = []
    state["guest_summaries"] = {}

    def _load_summary_parsed(summary_path: Path) -> dict[str, Any]:
        if summary_path.suffix == ".json":
            try:
                data = json.loads(summary_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
            return {
                "confirmed_points": filter_semantic_items(data.get("confirmed_points", [])),
                "conflicts": filter_semantic_items(data.get("conflicts", [])),
                "open_questions": filter_semantic_items(data.get("open_questions", [])),
                "guest_position_summary": data.get("guest_position_summary", ""),
                "suggested_next_question": data.get("suggested_next_question", ""),
            }
        parsed = parse_summary_sections(summary_path.read_text(encoding="utf-8"))
        for key in ("confirmed_points", "conflicts", "open_questions"):
            parsed[key] = filter_semantic_items(parsed.get(key, []))
        return parsed

    for entry in state.get("history", []):
        work_items: list[tuple[str, Path | None]] = []
        if entry.get("mode") == "parallel" and entry.get("entries"):
            for sub in entry["entries"]:
                if not sub.get("success"):
                    continue
                rel = sub.get("summary_json_path") or sub.get("summary_md_path") or sub.get("summary_path")
                path = meeting_dir / rel if rel else None
                work_items.append((sub.get("guest", "?"), path))
        else:
            rel = entry.get("summary_path") or entry.get("summary_json_path")
            work_items.append((entry.get("guest", "?"), meeting_dir / rel if rel else None))

        for guest, summary_path in work_items:
            if not summary_path or not summary_path.exists():
                continue
            parsed = _load_summary_parsed(summary_path)
            if not parsed:
                continue
            counts = apply_parsed_summary(state, guest, parsed)
            if parsed.get("suggested_next_question"):
                last_question = parsed["suggested_next_question"]
            if entry.get("mode") != "parallel":
                entry["confirmed_points_added"] = counts["confirmed_points_added"]
                entry["conflicts_added"] = counts["conflicts_added"]
                entry["open_questions_added"] = counts["open_questions_added"]

    state["confirmed_points"] = filter_semantic_items(state["confirmed_points"])
    state["conflicts"] = filter_semantic_items(state["conflicts"])
    state["open_questions"] = filter_semantic_items(state["open_questions"])
    state["next_question"] = last_question


def migrate_guest_names(meeting_dir: Path, state: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    for sub in ("prompts", "raw", "summaries"):
        folder = meeting_dir / sub
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            name = path.name
            for old, new in LEGACY_GUEST_MAP.items():
                token = f"-{old}."
                if token not in name:
                    continue
                target = path.with_name(name.replace(token, f"-{new}."))
                if target.exists() and target != path:
                    continue
                path.rename(target)
                changes.append(f"{path.relative_to(meeting_dir)} -> {target.relative_to(meeting_dir)}")
                if sub == "summaries":
                    text = target.read_text(encoding="utf-8")
                    text = re.sub(rf"^guest:\s*{re.escape(old)}\s*$", f"guest: {new}", text, flags=re.M)
                    text = text.replace(f"-{old}.md", f"-{new}.md")
                    target.write_text(text, encoding="utf-8")
                break

    def remap_guest(name: str) -> str:
        return LEGACY_GUEST_MAP.get(name, name)

    if state.get("next_speaker"):
        state["next_speaker"] = remap_guest(state["next_speaker"])

    new_summaries: dict[str, str] = {}
    for guest, summary in state.get("guest_summaries", {}).items():
        new_summaries[remap_guest(guest)] = summary
    state["guest_summaries"] = new_summaries

    for entry in state.get("history", []):
        targets: list[dict[str, Any]] = []
        if entry.get("mode") == "parallel" and entry.get("entries"):
            targets.extend(entry["entries"])
        elif "guest" in entry:
            targets.append(entry)

        for target in targets:
            if "guest" not in target:
                continue
            old_guest = target["guest"]
            target["guest"] = remap_guest(old_guest)
            for key in (
                "prompt_path",
                "raw_output_path",
                "summary_path",
                "summary_md_path",
                "summary_json_path",
            ):
                if key in target:
                    for old, new in LEGACY_GUEST_MAP.items():
                        target[key] = target[key].replace(f"-{old}.", f"-{new}.")

    return changes
