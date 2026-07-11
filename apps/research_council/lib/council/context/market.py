"""Market context I/O and equity symbol extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from missionos.context import ContextPack

_EMPTY_CONTEXT_MSG = '(暂无共享市场上下文。请运行: ./council.sh context "范围")'

EQUITY_ALIASES: dict[str, str] = {
    "特斯拉": "TSLA",
    "苹果": "AAPL",
    "英伟达": "NVDA",
    "谷歌": "GOOGL",
    "微软": "MSFT",
    "亚马逊": "AMZN",
    "meta": "META",
}

_EQUITY_STOPWORDS = frozenset({"USD", "CNY", "ETF", "GDP", "CPI", "FOMC", "OPEC", "DXY", "VIX"})

MACRO_ALIASES: dict[str, tuple[str, str]] = {
    "黄金": ("GC=F", "黄金"),
    "gold": ("GC=F", "黄金"),
    "xau": ("GC=F", "黄金"),
    "美元": ("DX-Y.NYB", "美元指数"),
    "美元指数": ("DX-Y.NYB", "美元指数"),
    "dxy": ("DX-Y.NYB", "美元指数"),
    "美债": ("^TNX", "10年期美债收益率"),
    "美债收益率": ("^TNX", "10年期美债收益率"),
    "10y": ("^TNX", "10年期美债收益率"),
    "收益率": ("^TNX", "10年期美债收益率"),
    "原油": ("CL=F", "WTI原油"),
    "oil": ("CL=F", "WTI原油"),
    "wti": ("CL=F", "WTI原油"),
    "vix": ("^VIX", "VIX恐慌指数"),
}


def read_market_context(meeting_dir: Path) -> str:
    context_dir = meeting_dir / "context"
    pack = ContextPack.load(context_dir)
    if pack is not None:
        body = pack.read_body(context_dir)
        if body:
            return body
    md = context_dir / "market_context.md"
    if md.exists():
        return md.read_text(encoding="utf-8").strip()
    return _EMPTY_CONTEXT_MSG


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


def extract_macro_feeds(scope: str, topic: str = "") -> list[tuple[str, str, str]]:
    """Return (label, yahoo_symbol, file_slug) for macro instruments mentioned in scope."""
    text = f"{scope} {topic}".lower()
    found: list[tuple[str, str, str]] = []
    seen_syms: set[str] = set()
    for alias, (sym, label) in MACRO_ALIASES.items():
        if alias.lower() in text and sym not in seen_syms:
            slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or sym.replace("^", "").replace("=", "")
            found.append((label, sym, slug))
            seen_syms.add(sym)
    return found


def context_lacks_verifiable_data(body: str) -> bool:
    if not body.strip():
        return True
    if body.count("数据缺失") >= 4:
        return True
    if "[MOCK/" in body[:300]:
        return True
    return False


def compose_context_from_script_feeds(
    *,
    scope: str,
    topic: str,
    today: str,
    feed_blocks: list[str],
) -> str:
    lines = [
        "# Market Context",
        "",
        "## 当前日期",
        today,
        "",
        "## 议题",
        topic,
        "",
        "## 范围",
        scope,
        "",
        "## 脚本采集行情（可验证，优先引用）",
        "",
        "\n\n---\n\n".join(feed_blocks),
        "",
        "## 过去两周市场背景",
        "见上方各品种 week_range / change_pct；勿编造未列数字。",
        "",
        "## 黄金",
        _section_from_feeds(feed_blocks, ("黄金", "GC=F")),
        "",
        "## 美元",
        _section_from_feeds(feed_blocks, ("美元指数", "DX-Y.NYB", "美元")),
        "",
        "## 美债",
        _section_from_feeds(feed_blocks, ("10年期", "^TNX", "美债")),
        "",
        "## 原油",
        _section_from_feeds(feed_blocks, ("WTI", "CL=F", "原油")),
        "",
        "## 需要人工复核的数据点",
        "- A股/港股/个股财报等未在本脚本覆盖范围内",
        "",
        "## Source Notes",
        "- Yahoo Finance via scripts/fetch_macro.py / fetch_equity.py",
        "- 采集时间见各 feed generated_at",
        "",
    ]
    return "\n".join(lines)


def _section_from_feeds(blocks: list[str], keywords: tuple[str, ...]) -> str:
    for block in blocks:
        if any(k in block for k in keywords):
            for line in block.splitlines():
                if line.startswith("- price:") or line.startswith("- change_pct:"):
                    return line.replace("- ", "")
            return "见上方 Macro Data Feed 快照"
    return "数据缺失：范围未请求或 API 失败"


def extract_equity_symbols(scope: str, topic: str = "") -> list[str]:
    text = f"{scope} {topic}"
    found: list[str] = []
    lowered = text.lower()
    for alias, sym in EQUITY_ALIASES.items():
        if alias.lower() in lowered:
            found.append(sym)
    for match in re.findall(r"\b([A-Z]{2,5})\b", text):
        if match not in _EQUITY_STOPWORDS:
            found.append(match)
    return list(dict.fromkeys(found))