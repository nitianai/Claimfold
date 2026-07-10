#!/usr/bin/env python3
"""Fetch equity market data for context enrichment (placeholder).

Usage:
  python3 scripts/fetch_equity.py TSLA
  python3 scripts/fetch_equity.py TSLA --out meetings/<id>/context/tsla_data.md

Phase 2: wire yfinance or internal data API. Output is markdown for market_context merge.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


def fetch_symbol(symbol: str) -> str:
    # Placeholder — replace with real data source in Phase 2
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""# Equity Data Feed — {symbol.upper()}

generated_at: {now}
source: placeholder (scripts/fetch_equity.py)

> 【数据缺失】尚未接入行情 API。请安装数据源后替换本脚本，或手动补充。

symbol: {symbol.upper()}
status: pending_integration
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch equity data for Claimfold context")
    parser.add_argument("symbol", help="Ticker e.g. TSLA")
    parser.add_argument("--out", help="Output markdown path")
    args = parser.parse_args()

    body = fetch_symbol(args.symbol.strip())
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        print(f"Wrote: {path}")
    else:
        print(body)


if __name__ == "__main__":
    main()