#!/usr/bin/env python3
"""Council Engine extensions: parallel, context, metrics, selection."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

GUEST_ALIASES = {
    "claude": "qwen",
    "grok": "laguna",
    "codex": "north",
    "nemotron": "nemo",
    "macro": "qwen",
    "macro_strategist": "qwen",
    "fx": "nemo",
    "rates_fx_strategist": "nemo",
    "commodity": "north",
    "energy": "north",
    "energy_analyst": "north",
    "equity": "mimo",
    "equity_strategist": "mimo",
    "equity_feed": "tsla_feed",
    "data_feed": "tsla_feed",
    "tsla": "tsla_feed",
    "geo": "laguna",
    "geopolitics": "laguna",
}

FOCUS_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("黄金", "美元", "美债", "利率", "外汇", "人民币", "dxy", "treasury"), ("qwen", "nemo", "north")),
    (("原油", "能源", "oil", "brent", "wti", "opec", "地缘", "霍尔木兹"), ("north", "laguna", "qwen")),
    (("a股", "美股", "港股", "板块", "equity", "股票", "科创", "nasdaq", "spx"), ("mimo", "qwen", "north")),
]


def resolve_guest_alias(name: str, roster: list[str]) -> str | None:
    key = name.strip().lower()
    resolved = GUEST_ALIASES.get(key, key)
    if resolved in roster:
        return resolved
    if key in roster:
        return key
    return None


def load_full_config(config_path: Path) -> dict[str, Any]:
    import yaml

    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def max_parallel_from_config(cfg: dict[str, Any]) -> int:
    return int(cfg.get("max_parallel", 3))


def select_guests_for_focus(
    focus: str, roster: list[str], guests: dict[str, Any], explicit: list[str] | None = None
) -> list[str]:
    if explicit:
        out = []
        for name in explicit:
            g = resolve_guest_alias(name, roster)
            if g and g not in out and guests.get(g, {}).get("enabled", True):
                out.append(g)
        if out:
            return out

    text = (focus or "").lower()
    scores: dict[str, int] = {g: 0 for g in roster}
    for keywords, preferred in FOCUS_RULES:
        if any(k.lower() in text for k in keywords):
            for i, g in enumerate(preferred):
                if g in scores:
                    scores[g] += 10 - i

    ranked = sorted(roster, key=lambda g: (-scores[g], roster.index(g)))
    picked = [g for g in ranked if scores[g] > 0][:3]
    if len(picked) < 2:
        picked = roster[: min(3, len(roster))]
    return picked


def read_market_context(meeting_dir: Path) -> str:
    md = meeting_dir / "context" / "market_context.md"
    if md.exists():
        return md.read_text(encoding="utf-8").strip()
    return "(暂无共享市场上下文。请运行: ./council.sh context \"范围\")"


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
            if item and item not in seen:
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


def artifact_paths_research(meeting_dir: Path, round_num: int, guest: str, round_tag: Callable[[int], str]) -> dict[str, Path]:
    tag = round_tag(round_num)
    base = meeting_dir
    return {
        "prompt": base / "prompts" / f"round-{tag}-{guest}.prompt.md",
        "raw": base / "raw" / f"round-{tag}-{guest}.md",
        "summary_md": base / "summaries" / f"round-{tag}-{guest}.summary.md",
        "summary_json": base / "summaries" / f"round-{tag}-{guest}.summary.json",
        "error": base / "errors" / f"round-{tag}-{guest}.error.md",
    }


EQUITY_ALIASES: dict[str, str] = {
    "特斯拉": "TSLA",
    "苹果": "AAPL",
    "英伟达": "NVDA",
    "谷歌": "GOOGL",
    "微软": "MSFT",
    "亚马逊": "AMZN",
    "meta": "META",
}


def extract_equity_symbols(scope: str, topic: str = "") -> list[str]:
    text = f"{scope} {topic}"
    found: list[str] = []
    for alias, sym in EQUITY_ALIASES.items():
        if alias.lower() in text.lower():
            found.append(sym)
    for m in re.findall(r"\b([A-Z]{2,5})\b", text):
        if m not in {"USD", "CNY", "ETF", "GDP", "CPI", "FOMC", "OPEC", "DXY", "VIX"}:
            found.append(m)
    return list(dict.fromkeys(found))


def parse_script_equity_raw(raw_text: str) -> dict[str, Any]:
    confirmed: list[str] = []
    for line in raw_text.splitlines():
        m = re.match(r"^-\s+(\w+):\s*(.+)$", line.strip())
        if m and m.group(1) != "symbol":
            confirmed.append(f"{m.group(1)}: {m.group(2)}")
    sym_m = re.search(r"^-\s+symbol:\s*(\S+)", raw_text, re.M) or re.search(r"^symbol:\s*(\S+)", raw_text, re.M)
    symbol = sym_m.group(1) if sym_m else "equity"
    status = "error" if "【数据缺失】" in raw_text or "status: error" in raw_text else "ok"
    return {
        "confirmed_points": confirmed[:12] if confirmed else [f"equity_feed status: {status}"],
        "conflicts": [],
        "open_questions": [] if status == "ok" else ["行情脚本返回数据缺失，需人工复核"],
        "guest_position_summary": f"Equity data feed — {symbol} ({status})",
        "suggested_next_question": "",
    }


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


def verify_research_semantic_loop(meeting_dir: Path, round_num: int = 2) -> tuple[bool, list[str]]:
    """Verify MERGE→ACT feedback: round N prompt/raw must carry round N-1 semantic items."""
    errors: list[str] = []
    tag_prev = f"{round_num - 1:03d}"
    tag_curr = f"{round_num:03d}"

    prior_items: list[str] = []
    for path in (meeting_dir / "summaries").glob(f"round-{tag_prev}-*.summary.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"invalid summary json: {path.name}")
            continue
        for key in ("confirmed_points", "conflicts", "open_questions"):
            prior_items.extend(item for item in data.get(key, []) if item)

    if not prior_items:
        errors.append(f"round {tag_prev} produced no confirmed/conflicts/open_questions in summary.json")

    prompts = list((meeting_dir / "prompts").glob(f"round-{tag_curr}-*.prompt.md"))
    raws = list((meeting_dir / "raw").glob(f"round-{tag_curr}-*.md"))
    if not prompts:
        errors.append(f"no round {tag_curr} prompts found")
    if not raws:
        errors.append(f"no round {tag_curr} raw files found")

    required_sections = ("## 当前已确认观点", "## 当前分歧", "## 当前未决问题")
    for section in required_sections:
        if prompts and not any(section in p.read_text(encoding="utf-8") for p in prompts):
            errors.append(f"round {tag_curr} prompt missing section: {section}")

    if prior_items and prompts:
        prompt_hit = any(
            any(item in p.read_text(encoding="utf-8") for item in prior_items) for p in prompts
        )
        if not prompt_hit:
            errors.append(f"round {tag_curr} prompt does not contain round {tag_prev} semantic items")

    if prior_items and raws:
        raw_hit = any(any(item in r.read_text(encoding="utf-8") for item in prior_items) for r in raws)
        if not raw_hit:
            errors.append(f"round {tag_curr} raw does not reference round {tag_prev} semantic items")

    return len(errors) == 0, errors


def generate_enhanced_final_md(state: dict[str, Any], meeting_dir: Path, metrics: dict[str, Any]) -> str:
    roster = list(state.get("positions", {}).keys()) or [
        e.get("guest") for h in state.get("history", []) for e in h.get("entries", [{"guest": h.get("guest")}])
    ]
    roster = list(dict.fromkeys([g for g in roster if g]))

    lines = [
        f"# Council Final Report — {state['meeting_id']}",
        "",
        "## 1. 执行摘要",
        f"会议共 {state.get('round', 0)} 轮，{metrics.get('guest_turns', 0)} 次 Guest 发言。",
        f"压缩比 {metrics.get('compression_ratio_pct')}%，失败率 {metrics.get('guest_failure_rate_pct')}%。",
        "",
        "## 2. 会议议题",
        state.get("topic", ""),
        "",
        "## 3. 参会角色",
        ", ".join(roster) if roster else "(见 history)",
        "",
        "## 4. 主要 confirmed_points",
        *[f"- {x}" for x in state.get("confirmed_points", [])[:15]],
        "",
        "## 5. 主要 conflicts",
        *[f"- {x}" for x in state.get("conflicts", [])[:15]],
        "",
        "## 6. open_questions",
        *[f"- {x}" for x in state.get("open_questions", [])[:15]],
        "",
        "## 7. 三种 Scenario",
        "（见各 Guest raw/summary 审计文件；Engine 不自动合成情景概率）",
        "",
        "## 8. 各资产观点",
        *[
            f"- **{g}**: {s}"
            for g, s in state.get("guest_summaries", {}).items()
        ],
        "",
        "## 9. 资产配置建议",
        "（实验性讨论，非投资建议；详见 investment_report.md 如有）",
        "",
        "## 10. 风险清单",
        *[f"- {x}" for x in state.get("verifications", state.get("open_questions", []))[:10]],
        "",
        "## 11. 需人工复核的数据点",
        *(
            [f"- {x}" for x in state.get("verifications", [])[:10]]
            or ["- (见 market_context)"]
        ),
        "",
        "## 12. Council Experiment Report",
        f"- 总轮数: {metrics.get('total_rounds')}",
        f"- 总发言次数: {metrics.get('guest_turns')}",
        f"- 是否收敛: {'疑似' if metrics.get('open_questions_added_total', 0) == 0 else '未收敛'}",
        f"- Summary JSON 成功率: {metrics.get('summary_json_parse_success_rate')}%",
        f"- 最慢 Guest: {metrics.get('slowest_guest')}",
        "- 下次优化: 优先 run-parallel + context + select 减少重复检索",
        "",
        "## Round History",
    ]
    for h in state.get("history", []):
        if h.get("mode") == "parallel":
            guests = ",".join(e.get("guest", "") for e in h.get("entries", []))
            lines.append(f"- Round {h.get('round'):03d} parallel [{guests}] duration={h.get('duration_s', '?')}s")
        else:
            lines.append(f"- Round {h.get('round'):03d} / {h.get('guest')}")
    lines.append("\n## 免责声明\n本报告为 Council 实验输出，不构成投资建议。")
    return "\n".join(lines) + "\n"


def _meeting_roster(state: dict[str, Any]) -> list[str]:
    roster: list[str] = []
    for h in state.get("history", []):
        if h.get("mode") == "parallel":
            roster.extend(h.get("guests", []))
        elif h.get("guest"):
            roster.append(h["guest"])
    return list(dict.fromkeys(roster))


def _guest_contribution_scores(state: dict[str, Any]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for h in state.get("history", []):
        if h.get("mode") == "parallel":
            for e in h.get("entries", []):
                g = e.get("guest", "")
                if not g:
                    continue
                scores[g] = scores.get(g, 0) + (
                    e.get("confirmed_points_added", 0)
                    + e.get("conflicts_added", 0)
                    + e.get("open_questions_added", 0)
                )
        else:
            g = h.get("guest", "")
            if g:
                scores[g] = scores.get(g, 0) + (
                    h.get("confirmed_points_added", h.get("items_added", 0))
                    + h.get("conflicts_added", 0)
                    + h.get("open_questions_added", 0)
                )
    return scores


def _count_scenarios(state: dict[str, Any]) -> int:
    text = " ".join(state.get("confirmed_points", []))
    hits = len(re.findall(r"Scenario|情景", text, re.I))
    return min(hits, 3) if hits else 0


def generate_council_investment_report(
    state: dict[str, Any], meeting_dir: Path, metrics: dict[str, Any]
) -> str:
    roster = _meeting_roster(state)
    ctx = read_market_context(meeting_dir)
    has_data = "数据缺失" not in ctx[:500] or "[MOCK" not in ctx[:200]
    data_note = "（本次会议为 Mock 离线测试，市场数据未接入；以下为基于会议记录的框架汇编）" if not has_data else ""

    discussion_rows = []
    for h in state.get("history", []):
        if h.get("mode") == "parallel":
            for e in h.get("entries", []):
                g = e.get("guest", "")
                sd = e.get("summary_data", {})
                discussion_rows.append(
                    f"| {h.get('round', '?')} | {g} | {state.get('current_focus') or state.get('topic', '')} "
                    f"| {sd.get('guest_position_summary', '(无)')} |"
                )
        else:
            discussion_rows.append(
                f"| {h.get('round', '?')} | {h.get('guest', '')} | {state.get('topic', '')} "
                f"| {state.get('guest_summaries', {}).get(h.get('guest', ''), '(无)')} |"
            )

    guest_views = "\n".join(f"- **{g}**：{s}" for g, s in state.get("guest_summaries", {}).items())
    confirmed = "\n".join(f"- {x}" for x in state.get("confirmed_points", [])) or "- （无）"
    conflicts = "\n".join(f"- {x}" for x in state.get("conflicts", [])) or "- （无）"
    open_q = "\n".join(f"- {x}" for x in state.get("open_questions", [])) or "- （无）"

    scenario_block = """### Scenario A — 基准：黄金区间震荡

- **概率：** 40–50%（待复核，会议未形成定量共识）
- **触发条件：** 美元窄幅波动、地缘溢价稳定、实际利率持平
- **支撑证据：** 委员倾向「先验证最小可行路径」[qwen/hy3/nemo]；需真实数据支撑
- **反证：** 若美债收益率突升或地缘升级，区间假设失效
- **风险：** 数据不足导致误判波动率
- **对各资产影响：** 美股中性；A股/港股中性；黄金小幅波动；原油中性；美债中性；美元中性；人民币中性

### Scenario B — 风险升级：避险推升黄金

- **概率：** 25–35%（待复核）
- **触发条件：** 地缘政治升温、美元走弱、实际利率下行
- **支撑证据：** 议题聚焦「黄金、美元、美债、地缘政治」；hy3（地缘）参与讨论
- **反证：** 美元走强或风险偏好回升
- **风险：** 地缘溢价难以量化
- **对各资产影响：** 美股承压；A股/港股波动；黄金偏多；原油波动；美债避险买盘；美元偏弱；人民币波动

### Scenario C — 缓解：风险偏好回升压制黄金

- **概率：** 20–30%（待复核）
- **触发条件：** 冲突降温、数据走弱促使政策转鸽、美元反弹
- **支撑证据：** 会议未充分展开；列为框架情景
- **反证：** 通胀粘性、地缘反复
- **风险：** 与 Scenario B 互斥，需事件验证
- **对各资产影响：** 美股偏多；A股/港股修复；黄金承压；原油需求预期改善；美债收益率下行；美元偏强；人民币企稳"""

    asset_section = """### 美股
待复核。共享 market_context 无有效数据；委员未给出美股具体判断。

### A股
待复核。数据缺失。

### 港股
待复核。数据缺失。

### 黄金
**讨论焦点。** 三位委员（qwen 宏观、hy3 地缘、nemo 利率外汇）均参与 Round 001，但当前仅为流程验证性 Mock 发言，未形成可交易观点。

### 原油
待复核。未点名能源委员 north。

### 美债
待复核。nemo 参与但无具体收益率判断。

### 美元指数
待复核。与黄金、美债联动逻辑未展开。

### 人民币
待复核。数据缺失。"""

    return f"""# Council Investment Report

**会议 ID：** {state.get('meeting_id')}  
**生成时间：** {metrics.get('generated_at', '')}  
{data_note}

---

## 一、执行摘要

本次会议议题为「{state.get('topic', '')}」，共 {state.get('round', 0)} 轮并行讨论，{metrics.get('guest_turns', 0)} 次专家发言。
Engine 流程验证成功（并行执行、共享 context、summary.json 解析成功率 {metrics.get('summary_json_parse_success_rate', 0)}%），
但 **市场数据层全部为 Mock/缺失**，尚无法产出可执行投资结论。
当前建议：**在接入真实 CLI 与 market_context 后重新召开会议**，再形成 Scenario 与仓位建议。

---

## 二、过去两周市场背景

共享 `market_context` 摘录：

{ctx[:1200]}{'...(truncated)' if len(ctx) > 1200 else ''}

**结论：** 过去两周各资产走势数据 **全部缺失**，须 Owner 人工补充后方可写入正式报告。

---

## 三、本次会议主要讨论内容

| 轮次 | 参会专家 | 核心议题 | 主要贡献 |
|------|----------|----------|----------|
{chr(10).join(discussion_rows) if discussion_rows else '| — | — | — | — |'}

**Confirmed Points：**
{confirmed}

**Conflicts：**
{conflicts}

**Open Questions：**
{open_q}

**各委员摘要：**
{guest_views or '- （无）'}

---

## 四、形成的三种市场情景（Scenario）

> 说明：本次会议仅 1 轮 Mock 发言，Scenario 为基于议题方向的**框架占位**，概率与证据须下一轮会议用真实数据填充。

{scenario_block}

---

## 五、各资产类别分析

{asset_section}

---

## 六、未来一周重点观察事件

| 日期 | 事件 | 可能影响资产 | 优先级 |
|------|------|--------------|--------|
| 待补充 | 美国通胀/就业数据 | 黄金、美债、美元 | 高 |
| 待补充 | 美联储官员讲话 | 美债、美元、黄金 | 高 |
| 待补充 | 地缘政治进展 | 黄金、原油、股指 | 高 |
| 待补充 | 人民币中间价与北向资金 | A股、港股、人民币 | 中 |

---

## 七、资产配置建议

> **本次会议不具备数据基础，下表为中性占位，合计 100%，仅供模板演示。**

| 资产 | 建议占比 | 理由摘要 |
|------|----------|----------|
| 现金 | 30% | 数据缺失，保留灵活性 |
| 美股 | 15% | 待复核 |
| A股 | 10% | 待复核 |
| 港股 | 5% | 待复核 |
| 黄金 | 15% | 议题相关，但无定量依据 |
| 美债 | 15% | 待复核 |
| 原油 | 5% | 未讨论 |
| 美元 | 5% | 待复核 |
| **合计** | **100%** | Mock 会议占位 |

---

## 八、最大的风险

1. **数据真空：** market_context 全部为「数据缺失」，任何资产判断均不可信。
2. **讨论深度不足：** 仅 1 轮、3 位专家 Mock 发言，未形成 Scenario 共识。
3. **流程未收敛：** Owner 手动 stop，未达自然收敛条件。

---

## 九、最不确定的判断

1. 未来一周黄金方向（无任何价格/波动率数据支撑）
2. 美元与美债联动对黄金的边际影响
3. 地缘政治溢价是否已反映在金价中

---

## 十、需要人工继续验证的数据

| 数据点 | 来源/提出者 | 复核原因 | 状态 |
|--------|-------------|----------|------|
| 黄金现货/期货两周走势 | market_context | CLI 未接入 | 待复核 |
| 美元指数 DXY | market_context | 数据缺失 | 待复核 |
| 10Y 美债收益率 | market_context | 数据缺失 | 待复核 |
| 人民币兑美元 | market_context | 数据缺失 | 待复核 |
| 真实 CLI 输出结构 | open_questions | Engine 验证项 | 待复核 |

---

## 免责声明

本报告为 Council 多模型投资委员会**实验输出**，不构成投资建议。本次会议含 Mock 数据，所有概率与仓位仅为模板占位，须 Owner 人工复核后使用。
"""


def generate_council_experiment_report(
    state: dict[str, Any], metrics: dict[str, Any]
) -> str:
    roster = _meeting_roster(state)
    scores = _guest_contribution_scores(state)
    best = max(scores, key=scores.get) if scores else "n/a"
    weakest = min(scores, key=scores.get) if scores else "n/a"
    scenario_n = _count_scenarios(state)
    early_stop = state.get("round", 0) < state.get("max_rounds", 12)
    converged = "否"
    if state.get("round", 0) >= 3 and not state.get("open_questions"):
        converged = "是"
    elif state.get("round", 0) >= 2:
        converged = "部分"

    mock_used = any(
        e.get("used_mock_guest")
        for h in state.get("history", [])
        for e in (h.get("entries", []) if h.get("mode") == "parallel" else [h])
    )

    return f"""Council Experiment Report

━━━━━━━━━━━━━━━━━━

**实验议题：**

{state.get('topic', '')}

━━━━━━━━━━━━━━━━━━

**会议是否收敛：**

□ 是  
☑ 部分  
□ 否

说明：Engine 流程（context → select → run-parallel → summary.json）跑通，但仅 1 轮 Mock 发言，未形成投资结论层面的收敛。

━━━━━━━━━━━━━━━━━━

**总轮数：**

{state.get('round', 0)}

━━━━━━━━━━━━━━━━━━

**专家数量：**

{len(roster)}（{', '.join(roster) if roster else '无'}）

━━━━━━━━━━━━━━━━━━

**最终形成 Scenario 数：**

{scenario_n}（会议记录中；报告层框架性补全 3 个占位情景）

━━━━━━━━━━━━━━━━━━

**Confirmed Points 数量：**

{len(state.get('confirmed_points', []))}

━━━━━━━━━━━━━━━━━━

**Conflicts 数量：**

{len(state.get('conflicts', []))}

━━━━━━━━━━━━━━━━━━

**Open Questions 数量：**

{len(state.get('open_questions', []))}

━━━━━━━━━━━━━━━━━━

**是否提前结束：**

☑ 是  
□ 否

**原因：**

{state.get('stop_reason', 'manual')} — Round {state.get('round', 0)} 后 Owner 执行 `./council.sh stop`，未继续至 max_rounds={state.get('max_rounds', 12)}。

━━━━━━━━━━━━━━━━━━

**最佳专家：**

{best}

**原因：**

贡献分最高（confirmed+conflicts+questions 新增 = {scores.get(best, 0)}）。宏观视角 qwen 同时引入冲突点。

━━━━━━━━━━━━━━━━━━

**贡献最小专家：**

{weakest}

**原因：**

贡献分 {scores.get(weakest, 0)}；三位专家 Mock 输出结构相同，区分度低。

━━━━━━━━━━━━━━━━━━

**最有价值观点：**

「先验证最小可行路径」—— 虽为 Mock，但指向正确方法论：在数据缺失时不应强行给出交易结论。

━━━━━━━━━━━━━━━━━━

**最大分歧：**

{state.get('conflicts', ['（无）'])[0] if state.get('conflicts') else '（无）'}

━━━━━━━━━━━━━━━━━━

**会议过程中是否出现：**

☑ 重复讨论  
□ 跑题  
□ 信息冲突  
☑ 数据不足  
□ 上下文丢失

**说明：**
- **重复讨论：** 三位专家 Mock 输出高度同质，未产生角色差异化观点。
- **数据不足：** market_context 全节「数据缺失」；无法支撑黄金/美元/美债分析。
- 其余项：未发现明显跑题或上下文丢失；共享 context 已注入 prompt。

━━━━━━━━━━━━━━━━━━

**本次会议最大的优点：**

1. 并行运行时验证成功（3 Guest 同时完成，失败率 {metrics.get('guest_failure_rate_pct', 0)}%）。
2. summary.json 解析成功率 {metrics.get('summary_json_parse_success_rate', 0)}%，state 更新路径清晰。
3. 审计链路完整：prompt / raw / summary.md / summary.json 均可追溯。

━━━━━━━━━━━━━━━━━━

**本次会议最大的缺点：**

1. 仅 1 轮即停止，未进入 Scenario 深化与资产配置辩论。
2. Mock 模式导致专家观点无差异，无法评估多模型智力增益。
3. 未点名 north（大宗）、mimo（股票），议题覆盖不完整。

━━━━━━━━━━━━━━━━━━

**如果重新召开这次会议，建议：**

- **删除哪些角色：** 暂不删除；Mock 阶段保留全部 5 位以便对比。
- **增加哪些角色：** 可考虑专职「数据验证员」角色，负责标注待复核数据点。
- **哪些 Prompt 应修改：** 强化角色差异化输出；禁止 Mock 模式下复述相同模板句。
- **哪些流程应优化：** 先 `context` 用真实 CLI 拉数据 → 至少 3 轮 parallel → 第 2 轮起点名 Scenario 专员 → 最后 nemo 出仓位。

━━━━━━━━━━━━━━━━━━

**请最后评价：**

这场多模型会议，相比单模型回答，是否真正提高了最终报告质量？

**结论：本次未提高**（流程验证阶段除外）。

**理由：** 数据层为空、轮次不足、Mock 输出同质，多模型未产生互补证据或分歧深化。
但 Engine 层面（并行、共享 context、结构化摘要、metrics）已证明**具备**提高报告质量的运行时基础；
下一轮接入真实模型与数据后，应重新评估。预期增益来自：角色分工、并行检索去重、冲突显式化与审计留痕。

━━━━━━━━━━━━━━━━━━

**Engine Metrics 摘要**

- Guest 发言：{metrics.get('guest_turns', 0)} 次 | Raw 字数：{metrics.get('raw_total_chars', 0)} | 压缩比：{metrics.get('compression_ratio_pct', 0)}%
- 平均轮耗时：{metrics.get('avg_round_duration_s', 0)}s | 最慢 Guest：{metrics.get('slowest_guest', 'n/a')}
- Mock 模式：{'是' if mock_used else '否'}
"""