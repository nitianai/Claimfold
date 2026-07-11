"""Summary JSON build, render, and state merge."""

from __future__ import annotations

import re
from typing import Any

from council.parsers.mock_filter import is_mock_semantic_item


def extract_numbers_dates_assets(text: str) -> dict[str, list[str]]:
    numbers = list(dict.fromkeys(re.findall(r"\$[\d,.]+|\d+\.?\d*%|¥[\d,.]+|\d{4}-\d{2}-\d{2}", text)))[:20]
    dates = list(dict.fromkeys(re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日", text)))[:15]
    tickers = list(
        dict.fromkeys(
            re.findall(
                r"\b(S&P 500|NASDAQ|DXY|WTI|Brent|沪深300|科创50|HSI|10Y|VIX|USD/CNY|CNH)\b",
                text,
                re.I,
            )
        )
    )[:15]
    return {"numbers_mentioned": numbers, "dates_mentioned": dates, "tickers_or_assets": tickers}


def build_summary_json(
    *,
    meeting_id: str,
    round_num: int,
    guest: str,
    parsed: dict[str, Any],
    raw_text: str,
) -> dict[str, Any]:
    meta = extract_numbers_dates_assets(raw_text)
    return {
        "meeting_id": meeting_id,
        "round": round_num,
        "guest": guest,
        "confirmed_points": parsed.get("confirmed_points", []),
        "conflicts": parsed.get("conflicts", []),
        "open_questions": parsed.get("open_questions", []),
        "guest_position_summary": parsed.get("guest_position_summary", ""),
        "suggested_next_question": parsed.get("suggested_next_question", ""),
        "numbers_mentioned": meta["numbers_mentioned"],
        "dates_mentioned": meta["dates_mentioned"],
        "tickers_or_assets": meta["tickers_or_assets"],
        "risks": [c for c in parsed.get("conflicts", []) if "risk" in c.lower()][:5],
        "confidence": None,
    }


def summary_json_to_md(data: dict[str, Any]) -> str:
    lines = [
        "---",
        f"meeting_id: {data.get('meeting_id')}",
        f"round: {data.get('round')}",
        f"guest: {data.get('guest')}",
        "summary_type: compressed",
        "---",
        "",
        "### confirmed_points",
        *[f"- {x}" for x in data.get("confirmed_points", [])],
        "",
        "### conflicts",
        *[f"- {x}" for x in data.get("conflicts", [])],
        "",
        "### open_questions",
        *[f"- {x}" for x in data.get("open_questions", [])],
        "",
        "### guest_position_summary",
        data.get("guest_position_summary", ""),
        "",
        "### suggested_next_question",
        data.get("suggested_next_question", ""),
    ]
    return "\n".join(lines) + "\n"


def apply_summary_json_to_state(state: dict[str, Any], data: dict[str, Any]) -> dict[str, int]:
    guest = data["guest"]
    cp_b = len(state.setdefault("confirmed_points", []))
    cf_b = len(state.setdefault("conflicts", []))
    oq_b = len(state.setdefault("open_questions", []))

    for key, target in (
        ("confirmed_points", "confirmed_points"),
        ("conflicts", "conflicts"),
        ("open_questions", "open_questions"),
    ):
        seen = set(state[target])
        for item in data.get(key, []):
            if item and not is_mock_semantic_item(item) and item not in seen:
                state[target].append(item)
                seen.add(item)

    if data.get("guest_position_summary"):
        state.setdefault("guest_summaries", {})[guest] = data["guest_position_summary"]
    if data.get("suggested_next_question") and not state.get("current_focus"):
        state["next_question"] = data["suggested_next_question"]

    return {
        "confirmed_points_added": len(state["confirmed_points"]) - cp_b,
        "conflicts_added": len(state["conflicts"]) - cf_b,
        "open_questions_added": len(state["open_questions"]) - oq_b,
    }