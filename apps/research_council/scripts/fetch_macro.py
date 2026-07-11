#!/usr/bin/env python3
"""Fetch macro market data (gold, USD, rates) for Claimfold context.

Usage:
  python3 scripts/fetch_macro.py GC=F --label 黄金
  python3 scripts/fetch_macro.py DX-Y.NYB --label 美元指数 --out meetings/<id>/context/usd_data.md

Uses Yahoo Finance chart API (stdlib only).
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1mo"
USER_AGENT = "Claimfold/1.0 (research-runtime; macro-data-script)"


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fmt_price(v: float | int | None, currency: str = "USD") -> str:
    if v is None:
        return "n/a"
    sym = "$" if currency.upper() == "USD" else f"{currency} "
    return f"{sym}{v:,.2f}"


def _pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.2f}%"


def fetch_instrument(symbol: str, *, label: str = "") -> tuple[str, dict]:
    sym = symbol.strip()
    display = label or sym
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta: dict = {
        "symbol": sym,
        "label": display,
        "generated_at": now,
        "source": "yahoo_finance",
        "status": "ok",
    }
    try:
        chart = _fetch_json(YAHOO_CHART.format(symbol=urllib.request.quote(sym, safe="^-$.")))
        result = chart["chart"]["result"][0]
        cm = result["meta"]
        currency = cm.get("currency", "USD")
        price = cm.get("regularMarketPrice")
        prev = cm.get("chartPreviousClose") or cm.get("previousClose")
        change_pct = ((price - prev) / prev * 100) if price and prev else None
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        valid = [c for c in closes if c is not None]
        week_low = min(valid[-5:]) if len(valid) >= 5 else (min(valid) if valid else None)
        week_high = max(valid[-5:]) if len(valid) >= 5 else (max(valid) if valid else None)

        meta.update(
            {
                "price": price,
                "currency": currency,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "week_low": week_low,
                "week_high": week_high,
            }
        )

        body = f"""# Macro Data Feed — {display} ({sym})

generated_at: {now}
source: yahoo_finance (scripts/fetch_macro.py)
status: ok

## Snapshot

- instrument: {display}
- symbol: {sym}
- price: {_fmt_price(price, currency)}
- change_pct: {_pct(change_pct)}
- week_range: {_fmt_price(week_low, currency)} – {_fmt_price(week_high, currency)}

> 证据层数据 — Guest 可引用上述数字；自行补充须标注【新增信息】。
"""
        return body, meta
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TypeError, ZeroDivisionError) as exc:
        meta["status"] = "error"
        meta["error"] = str(exc)
        body = f"""# Macro Data Feed — {display} ({sym})

generated_at: {now}
source: yahoo_finance (scripts/fetch_macro.py)
status: error

> 【数据缺失】行情 API 请求失败: {exc}

symbol: {sym}
"""
        return body, meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch macro data for Claimfold context")
    parser.add_argument("symbol", help="Yahoo symbol e.g. GC=F, DX-Y.NYB, ^TNX")
    parser.add_argument("--label", default="", help="Display label e.g. 黄金")
    parser.add_argument("--out", help="Output markdown path")
    parser.add_argument("--json", help="Output metadata JSON path")
    args = parser.parse_args()

    body, meta = fetch_instrument(args.symbol, label=args.label)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        print(f"Wrote: {path}")
    else:
        print(body)
    if args.json:
        jpath = Path(args.json)
        jpath.parent.mkdir(parents=True, exist_ok=True)
        jpath.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()