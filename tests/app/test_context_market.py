"""Tests for council.context.market."""

from __future__ import annotations

import tempfile
from pathlib import Path

from council.context.market import (
    compose_context_from_script_feeds,
    context_lacks_verifiable_data,
    extract_equity_symbols,
    extract_macro_feeds,
    read_market_context,
)
from missionos.context import ContextPack


def test_read_market_context_empty():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp)
        text = read_market_context(meeting_dir)
        assert "暂无共享市场上下文" in text


def test_read_market_context_from_context_pack():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp)
        context_dir = meeting_dir / "context"
        body = "# Market Context\n\nGold steady."
        ContextPack.write(
            context_dir,
            body=body,
            scope="gold",
            topic="macro",
            generated_at="2026-07-11T12:00:00Z",
        )
        assert read_market_context(meeting_dir) == body.strip()


def test_read_market_context_legacy_md_without_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp)
        context_dir = meeting_dir / "context"
        context_dir.mkdir(parents=True)
        (context_dir / "market_context.md").write_text("# Legacy\n", encoding="utf-8")
        assert read_market_context(meeting_dir) == "# Legacy"


def test_extract_equity_symbols_aliases_and_tickers():
    symbols = extract_equity_symbols("特斯拉与 NVDA", topic="关注 AAPL")
    assert symbols == ["TSLA", "NVDA", "AAPL"]


def test_extract_equity_symbols_skips_macro_stopwords():
    symbols = extract_equity_symbols("USD DXY CPI 黄金")
    assert "USD" not in symbols
    assert "DXY" not in symbols
    assert "CPI" not in symbols


def test_extract_macro_feeds_gold_usd_rates():
    feeds = extract_macro_feeds("黄金、美元指数、美债收益率", topic="黄金一周")
    symbols = {sym for _, sym, _ in feeds}
    assert "GC=F" in symbols
    assert "DX-Y.NYB" in symbols
    assert "^TNX" in symbols


def test_extract_macro_feeds_dedupes_symbols():
    feeds = extract_macro_feeds("黄金 gold XAU", topic="")
    assert len(feeds) == 1
    assert feeds[0][1] == "GC=F"


def test_context_lacks_verifiable_data_detects_sparse():
    assert context_lacks_verifiable_data("")
    assert context_lacks_verifiable_data("数据缺失\n数据缺失\n数据缺失\n数据缺失")
    assert context_lacks_verifiable_data("[MOCK/ context-collector]")
    assert not context_lacks_verifiable_data("- price: $2,400.00\n- change_pct: +1.2%")


def test_compose_context_from_script_feeds_includes_prices():
    block = """# Macro Data Feed — 黄金 (GC=F)
- price: $2,400.00
- change_pct: +1.20%
"""
    body = compose_context_from_script_feeds(
        scope="黄金、美元指数",
        topic="黄金一周",
        today="2026-07-11",
        feed_blocks=[block],
    )
    assert "price: $2,400.00" in body
    assert "黄金一周" in body
    assert "Yahoo Finance" in body