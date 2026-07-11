"""Meeting metrics computation and markdown rendering."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def compute_metrics(meeting_dir: Path, state: dict[str, Any], guests: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_chars = sum(len(p.read_text(encoding="utf-8")) for p in (meeting_dir / "raw").glob("*") if p.is_file())
    sum_chars = sum(len(p.read_text(encoding="utf-8")) for p in (meeting_dir / "summaries").glob("*.md") if p.is_file())
    json_files = list((meeting_dir / "summaries").glob("*.summary.json"))
    json_ok = 0
    for jf in json_files:
        try:
            json.loads(jf.read_text(encoding="utf-8"))
            json_ok += 1
        except json.JSONDecodeError:
            pass

    guest_turns = 0
    cp_added = cf_added = oq_added = 0
    durations: list[tuple[str, float]] = []
    failures = 0
    mock_turns = 0
    tier_stats: dict[str, dict[str, float | int]] = {}

    def tier_of(guest_name: str, entry: dict[str, Any]) -> str:
        if entry.get("model_tier"):
            return str(entry["model_tier"])
        if guests:
            return str(guests.get(guest_name, {}).get("model_tier", "unknown"))
        return "unknown"

    def bump_tier(tier: str, *, duration: float = 0, failed: bool = False, mocked: bool = False) -> None:
        bucket = tier_stats.setdefault(
            tier,
            {"turns": 0, "failures": 0, "mocks": 0, "total_duration_s": 0.0},
        )
        bucket["turns"] = int(bucket["turns"]) + 1
        bucket["total_duration_s"] = float(bucket["total_duration_s"]) + duration
        if failed:
            bucket["failures"] = int(bucket["failures"]) + 1
        if mocked:
            bucket["mocks"] = int(bucket["mocks"]) + 1

    for h in state.get("history", []):
        if h.get("mode") == "parallel" and "entries" in h:
            for e in h["entries"]:
                guest_turns += 1
                gname = e.get("guest", "?")
                tier = tier_of(gname, e)
                failed = not e.get("success")
                mocked = bool(e.get("used_mock_guest"))
                dur = float(e.get("duration_s") or 0)
                if failed:
                    failures += 1
                if mocked:
                    mock_turns += 1
                if dur:
                    durations.append((gname, dur))
                bump_tier(tier, duration=dur, failed=failed, mocked=mocked)
            cp_added += h.get("confirmed_points_added", 0)
            cf_added += h.get("conflicts_added", 0)
            oq_added += h.get("open_questions_added", 0)
        else:
            guest_turns += 1
            gname = h.get("guest", "?")
            tier = tier_of(gname, h)
            failed = h.get("success") is False or bool(h.get("validation_errors"))
            dur = float(h.get("duration_s") or 0)
            if failed:
                failures += 1
            if dur:
                durations.append((gname, dur))
            bump_tier(tier, duration=dur, failed=failed)
            cp_added += h.get("confirmed_points_added", h.get("items_added", 0))
            cf_added += h.get("conflicts_added", 0)
            oq_added += h.get("open_questions_added", 0)

    total_dur = sum(d for _, d in durations)
    slowest = max(durations, key=lambda x: x[1]) if durations else ("n/a", 0)
    compression = (sum_chars / raw_chars * 100) if raw_chars else 0

    model_tier_breakdown: dict[str, dict[str, float | int]] = {}
    for tier, bucket in tier_stats.items():
        turns = int(bucket["turns"])
        model_tier_breakdown[tier] = {
            "turns": turns,
            "failure_rate_pct": round(int(bucket["failures"]) / turns * 100, 1) if turns else 0.0,
            "mock_rate_pct": round(int(bucket["mocks"]) / turns * 100, 1) if turns else 0.0,
            "avg_duration_s": round(float(bucket["total_duration_s"]) / turns, 1) if turns else 0.0,
        }

    return {
        "meeting_id": state.get("meeting_id"),
        "total_rounds": state.get("round", 0),
        "guest_turns": guest_turns,
        "raw_total_chars": raw_chars,
        "summary_total_chars": sum_chars,
        "compression_ratio_pct": round(compression, 1),
        "confirmed_points_added_total": cp_added,
        "conflicts_added_total": cf_added,
        "open_questions_added_total": oq_added,
        "summary_json_count": len(json_files),
        "summary_json_parse_success_rate": round(json_ok / len(json_files) * 100, 1) if json_files else 100.0,
        "guest_failure_rate_pct": round(failures / guest_turns * 100, 1) if guest_turns else 0.0,
        "mock_guest_rate_pct": round(mock_turns / guest_turns * 100, 1) if guest_turns else 0.0,
        "avg_round_duration_s": round(total_dur / state.get("round", 1), 1) if state.get("round") else 0,
        "slowest_guest": slowest[0],
        "slowest_guest_duration_s": slowest[1],
        "model_tier_breakdown": model_tier_breakdown,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def metrics_markdown(m: dict[str, Any]) -> str:
    lines = [
        f"# Council Metrics — {m.get('meeting_id')}",
        "",
        f"- 总轮数: {m.get('total_rounds')}",
        f"- Guest 发言次数: {m.get('guest_turns')}",
        f"- Raw 总字数: {m.get('raw_total_chars')}",
        f"- Summary 总字数: {m.get('summary_total_chars')}",
        f"- 平均压缩比: {m.get('compression_ratio_pct')}%",
        f"- 累计新增 confirmed_points: {m.get('confirmed_points_added_total')}",
        f"- 累计新增 conflicts: {m.get('conflicts_added_total')}",
        f"- 累计新增 open_questions: {m.get('open_questions_added_total')}",
        f"- Summary JSON 解析成功率: {m.get('summary_json_parse_success_rate')}%",
        f"- Guest 失败率: {m.get('guest_failure_rate_pct')}%",
        f"- Mock Guest 率: {m.get('mock_guest_rate_pct', 0)}%",
        f"- 平均每轮耗时: {m.get('avg_round_duration_s')}s",
        f"- 最慢 Guest: {m.get('slowest_guest')} ({m.get('slowest_guest_duration_s')}s)",
        "",
    ]
    tiers = m.get("model_tier_breakdown") or {}
    if tiers:
        lines.extend(["## model_tier 分层", ""])
        for tier, stats in sorted(tiers.items()):
            lines.append(
                f"- **{tier}**: turns={stats.get('turns')}, "
                f"mock={stats.get('mock_rate_pct')}%, "
                f"fail={stats.get('failure_rate_pct')}%, "
                f"avg={stats.get('avg_duration_s')}s"
            )
        lines.append("")
    return "\n".join(lines)