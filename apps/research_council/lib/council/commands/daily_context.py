"""Council: context command — market context collection."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from council.context.market import (
    compose_context_from_script_feeds,
    context_lacks_verifiable_data,
    extract_equity_symbols,
    extract_macro_feeds,
)

from council.cli_runner import fetch_equity_context_block, fetch_macro_context_block, invoke_cli
from council.config import MARKET_CONTEXT_PROMPT
from council.formatting import render_template
from council.guests import load_guests
from council.mock import generate_mock_market_context
from council.parsers import strip_markdown_fences
from council.adapters.meeting_events import meeting_event_log, publish_context_written
from council.state_store import get_current_meeting_dir, load_state, save_state
from missionos.context import ContextPack
from missionos.utils import utc_now


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

    script_blocks: list[str] = []
    script_meta: list[dict] = []

    for label, sym, slug in extract_macro_feeds(scope, state.get("topic", "")):
        block, meta = fetch_macro_context_block(sym, meeting_dir, label=label, slug=slug)
        if meta.get("status") == "ok" or meta.get("ok"):
            script_blocks.append(block.strip())
            script_meta.append(meta)
            print(f"Macro data attached: {label} ({sym}) → context/macro_{slug}_data.md")

    for sym in extract_equity_symbols(scope, state.get("topic", "")):
        block, meta = fetch_equity_context_block(sym, meeting_dir)
        if meta.get("status") == "ok" or meta.get("ok"):
            script_blocks.append(block.strip())
            script_meta.append(meta)
            print(f"Equity data attached: {sym} → context/{sym.lower()}_data.md")

    if script_blocks:
        prompt = (
            prompt.strip()
            + "\n\n---\n\n## 已采集脚本数据（必须引用，勿重复检索）\n\n"
            + "\n\n---\n\n".join(script_blocks)
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
    if script_blocks and (used_mock or not body.strip() or context_lacks_verifiable_data(body)):
        body = compose_context_from_script_feeds(
            scope=scope,
            topic=state.get("topic", ""),
            today=today,
            feed_blocks=script_blocks,
        )
        used_mock = False
    elif used_mock or not body.strip():
        body = generate_mock_market_context(scope=scope, topic=state.get("topic", ""), label="mock")

    body = strip_markdown_fences(body)

    context_dir = meeting_dir / "context"
    md_path, manifest_path, json_path = ContextPack.write(
        context_dir,
        body=body,
        scope=scope,
        topic=state.get("topic", ""),
        generated_at=utc_now(),
        metadata={
            "date": today,
            "used_mock": used_mock,
            "script_feeds": script_meta,
            "macro_feeds": [m for m in script_meta if m.get("label")],
            "equity_feeds": [m for m in script_meta if not m.get("label")],
        },
    )

    state["current_focus"] = scope
    save_state(meeting_dir, state)

    pack = ContextPack.load(context_dir)
    checksum = pack.checksum if pack is not None else ""
    publish_context_written(
        meeting_event_log(meeting_dir, state.get("meeting_id", meeting_dir.name)),
        scope=scope,
        checksum=checksum,
        used_mock=used_mock,
        body_path=str(md_path.relative_to(meeting_dir)),
    )

    print(f"Market context saved: {md_path}")
    print(f"Context manifest: {manifest_path}")
    print(f"JSON index: {json_path}")
    if used_mock and not script_blocks:
        print("[MOCK] Context generated offline — verify data before decisions.")
    elif used_mock and script_blocks:
        print("[MOCK] LLM context offline; script feed data attached.")