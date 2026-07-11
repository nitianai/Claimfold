"""Guest JSON extraction, validation, and state merge."""
from __future__ import annotations

import json
import re
from typing import Any

from council.parsers.mock_filter import is_mock_semantic_item


def extract_json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in guest output")
    return json.loads(text[start : end + 1])


def validate_guest_json(data: dict[str, Any], *, guest_name: str, role_id: str, round_num: int) -> list[str]:
    errors: list[str] = []
    required = (
        "speaker",
        "role",
        "round",
        "focus",
        "position",
        "confidence",
        "evidence",
        "risks",
        "challenge_to",
        "challenge_question",
        "need_verification",
    )
    for key in required:
        if key not in data:
            errors.append(f"missing field: {key}")

    if data.get("speaker") != guest_name:
        errors.append(f"speaker must be {guest_name}")
    if data.get("role") != role_id:
        errors.append(f"role must be {role_id}")
    if data.get("round") != round_num:
        errors.append(f"round must be {round_num}")

    position = str(data.get("position", ""))
    if len(position) > 50:
        errors.append(f"position exceeds 50 chars ({len(position)})")

    if not isinstance(data.get("confidence"), int) or not (0 <= int(data["confidence"]) <= 100):
        errors.append("confidence must be integer 0-100")

    for field, max_items in (("evidence", 3), ("risks", 2), ("need_verification", 99)):
        val = data.get(field, [])
        if not isinstance(val, list):
            errors.append(f"{field} must be a list")
        elif field != "need_verification" and len(val) > max_items:
            errors.append(f"{field} exceeds max {max_items} items")

    return errors


def format_peer_positions(state: dict[str, Any], guest_name: str) -> str:
    positions = state.get("positions", {})
    if not positions:
        return "(无)"
    lines = []
    for speaker, record in positions.items():
        if speaker == guest_name:
            continue
        lines.append(
            f"- {speaker} ({record.get('role', '')}): "
            f"{record.get('position', '')} [confidence={record.get('confidence', '?')}]"
        )
    return "\n".join(lines) if lines else "(无)"


def merge_guest_json_into_state(state: dict[str, Any], data: dict[str, Any]) -> dict[str, int]:
    speaker = data["speaker"]
    before_verifications = len(state.setdefault("verifications", []))
    before_challenges = len(state.setdefault("challenges", []))
    old_position = state.setdefault("positions", {}).get(speaker, {}).get("position", "")

    state["positions"][speaker] = data
    state.setdefault("round_records", []).append(data)

    for item in data.get("evidence", []):
        if item and not is_mock_semantic_item(item) and item not in state.setdefault("confirmed_points", []):
            state["confirmed_points"].append(f"[{speaker}] {item}")

    for item in data.get("risks", []):
        if item and not is_mock_semantic_item(item) and item not in state.setdefault("conflicts", []):
            state["conflicts"].append(f"[{speaker}] risk: {item}")

    for item in data.get("need_verification", []):
        if item and not is_mock_semantic_item(item) and item not in state["verifications"]:
            state["verifications"].append(item)
            if item not in state.setdefault("open_questions", []):
                state["open_questions"].append(item)

    if data.get("challenge_to") and data.get("challenge_question"):
        challenge = {
            "speaker": speaker,
            "challenge_to": data["challenge_to"],
            "challenge_question": data["challenge_question"],
            "round": data.get("round"),
        }
        state["challenges"].append(challenge)

    state.setdefault("guest_summaries", {})[speaker] = data.get("position", "")

    items_added = 0
    if data.get("position") != old_position:
        items_added += 1
    items_added += len(state["verifications"]) - before_verifications
    items_added += len(state["challenges"]) - before_challenges

    return {"items_added": items_added}