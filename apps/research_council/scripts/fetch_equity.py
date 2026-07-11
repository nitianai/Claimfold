#!/usr/bin/env python3
"""Fetch equity market data for Claimfold context / script guests.

Usage:
  python3 scripts/fetch_equity.py TSLA
  python3 scripts/fetch_equity.py TSLA --out meetings/<id>/context/tsla_data.md

Output: markdown evidence block for market_context merge or Data Guest raw.
Uses Yahoo Finance chart API (stdlib only, no pip deps).
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1mo"
YAHOO_QUOTE = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
USER_AGENT = "Claimfold/1.0 (research-runtime; equity-data-script)"


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


def fetch_symbol(symbol: str) -> tuple[str, dict]:
    sym = symbol.strip().upper()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta: dict = {"symbol": sym, "generated_at": now, "source": "yahoo_finance", "status": "ok"}

    try:
        chart = _fetch_json(YAHOO_CHART.format(symbol=sym))
        result = chart["chart"]["result"][0]
        cm = result["meta"]
        currency = cm.get("currency", "USD")
        price = cm.get("regularMarketPrice")
        prev = cm.get("chartPreviousClose") or cm.get("previousClose")
        change_pct = ((price - prev) / prev * 100) if price and prev else None

        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        valid_closes = [c for c in closes if c is not None]
        week_low = min(valid_closes[-5:]) if len(valid_closes) >= 5 else (min(valid_closes) if valid_closes else None)
        week_high = max(valid_closes[-5:]) if len(valid_closes) >= 5 else (max(valid_closes) if valid_closes else None)
        month_low = min(valid_closes) if valid_closes else None
        month_high = max(valid_closes) if valid_closes else None

        quote_extra: dict = {}
        try:
            qd = _fetch_json(YAHOO_QUOTE.format(symbol=sym))
            q = (qd.get("quoteResponse", {}) or {}).get("result", [{}])[0]
            quote_extra = {
                "market_cap": q.get("marketCap"),
                "pe_ratio": q.get("trailingPE") or q.get("forwardPE"),
                "beta": q.get("beta"),
                "fifty_two_week_high": q.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": q.get("fiftyTwoWeekLow"),
                "volume": q.get("regularMarketVolume"),
                "avg_volume": q.get("averageDailyVolume3Month"),
                "earnings_timestamp": q.get("earningsTimestamp"),
            }
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError):
            pass

        meta.update(
            {
                "price": price,
                "currency": currency,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "week_low": week_low,
                "week_high": week_high,
                "month_low": month_low,
                "month_high": month_high,
                **{k: v for k, v in quote_extra.items() if v is not None},
            }
        )

        earnings_line = ""
        if quote_extra.get("earnings_timestamp"):
            ts = int(quote_extra["earnings_timestamp"])
            earnings_line = f"- next_earnings: {datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')}\n"

        body = f"""# Equity Data Feed — {sym}

generated_at: {now}
source: yahoo_finance (scripts/fetch_equity.py)
status: ok

## Snapshot

- symbol: {sym}
- price: {_fmt_price(price, currency)}
- change_pct: {_pct(change_pct)}
- week_range: {_fmt_price(week_low, currency)} – {_fmt_price(week_high, currency)}
- month_range: {_fmt_price(month_low, currency)} – {_fmt_price(month_high, currency)}
"""
        if quote_extra.get("fifty_two_week_low") and quote_extra.get("fifty_two_week_high"):
            body += f"- fifty_two_week: {_fmt_price(quote_extra['fifty_two_week_low'], currency)} – {_fmt_price(quote_extra['fifty_two_week_high'], currency)}\n"
        if quote_extra.get("pe_ratio"):
            body += f"- pe_ratio: {quote_extra['pe_ratio']:.1f}\n"
        if quote_extra.get("beta"):
            body += f"- beta: {quote_extra['beta']:.2f}\n"
        if quote_extra.get("market_cap"):
            body += f"- market_cap: ${quote_extra['market_cap']/1e9:.1f}B\n"
        if quote_extra.get("volume"):
            body += f"- volume: {quote_extra['volume']:,}\n"
        body += earnings_line
        body += "\n> 证据层数据 — Guest 可引用上述数字；自行补充须标注【新增信息】。\n"
        return body, meta

    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TypeError, ZeroDivisionError) as exc:
        meta["status"] = "error"
        meta["error"] = str(exc)
        body = f"""# Equity Data Feed — {sym}

generated_at: {now}
source: yahoo_finance (scripts/fetch_equity.py)
status: error

> 【数据缺失】行情 API 请求失败: {exc}

symbol: {sym}
"""
        return body, meta


def parse_equity_feed(text: str) -> dict[str, list[str]]:
    """Extract structured bullets from fetch_equity markdown for summary.json."""
    confirmed: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^-\s+(\w+):\s*(.+)$", line.strip())
        if m and m.group(1) not in ("symbol",):
            confirmed.append(f"{m.group(1)}: {m.group(2)}")
    sym_m = re.search(r"^symbol:\s*(\S+)", text, re.M)
    if sym_m and not any("symbol:" in c for c in confirmed):
        confirmed.insert(0, f"symbol: {sym_m.group(1)}")
    return {"confirmed_points": confirmed[:12], "conflicts": [], "open_questions": []}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch equity data for Claimfold context")
    parser.add_argument("symbol", help="Ticker e.g. TSLA")
    parser.add_argument("--out", help="Output markdown path")
    parser.add_argument("--json", help="Output metadata JSON path")
    args = parser.parse_args()

    body, meta = fetch_symbol(args.symbol.strip())
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