"""Lightweight meeting quality comparison for multi-guest experiments."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def _norm(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\[mock[^\]]*\]", "", text, flags=re.I)
    return text


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _unique_ratio(items: list[str], *, threshold: float = 0.82) -> dict[str, Any]:
    cleaned = [_norm(x) for x in items if x and _norm(x)]
    if not cleaned:
        return {"count": 0, "unique": 0, "ratio": 0.0, "duplicates": 0}
    unique: list[str] = []
    dup = 0
    for item in cleaned:
        if any(_similar(item, u) >= threshold for u in unique):
            dup += 1
        else:
            unique.append(item)
    return {
        "count": len(cleaned),
        "unique": len(unique),
        "ratio": round(len(unique) / len(cleaned), 3),
        "duplicates": dup,
    }


def analyze_meeting(meeting_dir: Path) -> dict[str, Any]:
    state = json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))
    raw_dir = meeting_dir / "raw"
    summaries_dir = meeting_dir / "summaries"

    guest_stats: list[dict[str, Any]] = []
    mock_guest = mock_sum = failed = 0
    total_dur = 0.0

    for hist in state.get("history", []):
        if hist.get("mode") != "parallel":
            continue
        for entry in hist.get("entries", []):
            guest = entry.get("guest", "?")
            if not entry.get("success"):
                failed += 1
            if entry.get("used_mock_guest"):
                mock_guest += 1
            if entry.get("used_mock_summarizer"):
                mock_sum += 1
            dur = float(entry.get("duration_s") or 0)
            total_dur += dur

            raw_path = meeting_dir / str(entry.get("raw_output_path", ""))
            raw_len = len(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else 0
            guest_stats.append(
                {
                    "guest": guest,
                    "duration_s": dur,
                    "mock_guest": bool(entry.get("used_mock_guest")),
                    "raw_chars": raw_len,
                    "cp_added": entry.get("confirmed_points_added", 0),
                    "cf_added": entry.get("conflicts_added", 0),
                    "oq_added": entry.get("open_questions_added", 0),
                }
            )

    cp = _unique_ratio(state.get("confirmed_points", []))
    cf = _unique_ratio(state.get("conflicts", []))
    oq = _unique_ratio(state.get("open_questions", []))

    json_ok = 0
    json_total = 0
    for jf in summaries_dir.glob("*.summary.json"):
        json_total += 1
        try:
            json.loads(jf.read_text(encoding="utf-8"))
            json_ok += 1
        except json.JSONDecodeError:
            pass

    turns = len(guest_stats)
    return {
        "meeting_id": state.get("meeting_id"),
        "topic": state.get("topic"),
        "rounds": state.get("round", 0),
        "guest_turns": turns,
        "total_duration_s": round(total_dur, 1),
        "avg_duration_s": round(total_dur / turns, 1) if turns else 0,
        "mock_guest_rate": round(mock_guest / turns, 3) if turns else 0,
        "mock_summarizer_rate": round(mock_sum / turns, 3) if turns else 0,
        "failure_rate": round(failed / turns, 3) if turns else 0,
        "summary_json_success": round(json_ok / json_total, 3) if json_total else 0,
        "confirmed_unique_ratio": cp["ratio"],
        "confirmed_duplicates": cp["duplicates"],
        "conflicts_unique_ratio": cf["ratio"],
        "open_questions_unique_ratio": oq["ratio"],
        "state_counts": {
            "confirmed_points": len(state.get("confirmed_points", [])),
            "conflicts": len(state.get("conflicts", [])),
            "open_questions": len(state.get("open_questions", [])),
        },
        "guest_stats": guest_stats,
    }


def compare_reports(*meeting_dirs: Path) -> str:
    rows = [analyze_meeting(d) for d in meeting_dirs]
    lines = [
        "# 多模型会议质量对比",
        "",
        "| 会议 | 嘉宾数 | 总耗时 | 均耗时 | Mock率 | 失败率 | 唯一CP比 | 唯一CF比 | CP数 | CF数 | OQ数 |",
        "|------|--------|--------|--------|--------|--------|----------|----------|------|------|------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['meeting_id']} | {r['guest_turns']} | {r['total_duration_s']}s | "
            f"{r['avg_duration_s']}s | {r['mock_guest_rate']:.0%} | {r['failure_rate']:.0%} | "
            f"{r['confirmed_unique_ratio']:.2f} | {r['conflicts_unique_ratio']:.2f} | "
            f"{r['state_counts']['confirmed_points']} | {r['state_counts']['conflicts']} | "
            f"{r['state_counts']['open_questions']} |"
        )
    lines.extend(["", "## 逐 Guest", ""])
    for r in rows:
        lines.append(f"### {r['meeting_id']} ({r['guest_turns']} guests)")
        for g in r["guest_stats"]:
            flag = " [MOCK]" if g["mock_guest"] else ""
            lines.append(
                f"- {g['guest']}{flag}: {g['duration_s']}s, raw={g['raw_chars']}ch, "
                f"+cp{g['cp_added']} +cf{g['cf_added']} +oq{g['oq_added']}"
            )
        lines.append("")
    return "\n".join(lines)