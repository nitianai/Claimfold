"""Council: context command — market context collection."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from runtime_ext import extract_equity_symbols

from council.cli_runner import fetch_equity_context_block, invoke_cli
from council.config import MARKET_CONTEXT_PROMPT
from council.formatting import render_template
from council.guests import load_guests
from council.mock import generate_mock_market_context
from council.parsers import strip_markdown_fences
from council.state_store import get_current_meeting_dir, load_state, save_state
from utils import utc_now


def cmd_context(args: argparse.Namespace) -> None:
    scope = args.scope.strip()
    if not scope:
        raise SystemExit("Scope cannot be empty.")

    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    guests = load_guests()
    (meeting_dir / "context").mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if MARKET_CONTEXT_PROMPT.exists():
        prompt = render_template(
            MARKET_CONTEXT_PROMPT,
            {"scope": scope, "topic": state.get("topic", ""), "date": today},
        )
    else:
        prompt = f"Collect market context for: {scope}\nTopic: {state.get('topic', '')}\nDate: {today}"

    equity_blocks: list[str] = []
    equity_meta: list[dict] = []
    for sym in extract_equity_symbols(scope, state.get("topic", "")):
        block, meta = fetch_equity_context_block(sym, meeting_dir)
        if meta.get("status") == "ok" or meta.get("ok"):
            equity_blocks.append(block.strip())
            equity_meta.append(meta)
            print(f"Equity data attached: {sym} → context/{sym.lower()}_data.md")

    if equity_blocks:
        prompt = (
            prompt.strip()
            + "\n\n---\n\n## 已采集脚本数据（必须引用，勿重复检索）\n\n"
            + "\n\n---\n\n".join(equity_blocks)
        )

    collector = guests.get(
        "context_collector",
        guests.get("mimo", guests.get("nemo", {})),
    )
    cmd = collector.get("command", "")
    timeout = int(collector.get("timeout_seconds", 90))
    body, used_mock = invoke_cli(
        cmd,
        prompt,
        mock_label="context-collector",
        round_num=state.get("round", 0),
        guest="context",
        kind="guest",
        timeout_seconds=timeout,
    )
    if (used_mock or not body.strip()) and equity_blocks:
        body = (
            f"# Market Context\n\n## 当前日期\n{today}\n\n## 议题\n{state.get('topic', '')}\n\n"
            f"## 范围\n{scope}\n\n"
            + "\n\n---\n\n".join(equity_blocks)
            + "\n\n## Source Notes\n- 脚本采集（fetch_equity.py）；宏观章节待 LLM 补全\n"
        )
        used_mock = False
    elif used_mock or not body.strip():
        body = generate_mock_market_context(scope=scope, topic=state.get("topic", ""), label="mock")

    body = strip_markdown_fences(body)

    md_path = meeting_dir / "context" / "market_context.md"
    json_path = meeting_dir / "context" / "market_context.json"
    md_path.write_text(body.strip() + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "scope": scope,
                "topic": state.get("topic", ""),
                "date": today,
                "used_mock": used_mock,
                "equity_feeds": equity_meta,
                "body_md": body.strip(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state["current_focus"] = scope
    save_state(meeting_dir, state)
    print(f"Market context saved: {md_path}")
    print(f"JSON index: {json_path}")
    if used_mock and not equity_blocks:
        print("[MOCK] Context generated offline — verify data before decisions.")
    elif used_mock and equity_blocks:
        print("[MOCK] LLM context offline; equity script data attached.")