"""Council: daily."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from council.context.market import extract_equity_symbols
from missionos.context import ContextPack
from missionos.utils import utc_now

from council.cli_runner import fetch_equity_context_block, invoke_cli
from council.config import ROOT
from council.formatting import format_list, round_tag
from council.guests import load_guests
from council.parsers import filter_semantic_items, strip_markdown_fences


def find_latest_prior_final(meetings_dir: Path, *, exclude_meeting_id: str = "") -> Path | None:
    best: tuple[float, Path] | None = None
    for meeting_path in meetings_dir.iterdir():
        if not meeting_path.is_dir():
            continue
        if meeting_path.name == exclude_meeting_id:
            continue
        final_path = meeting_path / "final.md"
        if not final_path.is_file():
            continue
        mtime = final_path.stat().st_mtime
        if best is None or mtime > best[0]:
            best = (mtime, final_path)
    return best[1] if best else None


def build_daily_context(
    meeting_dir: Path,
    state: dict[str, Any],
    scope: str,
    *,
    skip_llm: bool = True,
    prior_final: Path | None = None,
) -> dict[str, Any]:
    """14:30 日频：昨日盘后 + 今日脚本，默认跳过 context LLM。"""
    (meeting_dir / "context").mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M")

    equity_blocks: list[str] = []
    equity_meta: list[dict[str, Any]] = []
    for sym in extract_equity_symbols(scope, state.get("topic", "")):
        block, meta = fetch_equity_context_block(sym, meeting_dir)
        if meta.get("status") == "ok" or meta.get("ok"):
            equity_blocks.append(block.strip())
            equity_meta.append(meta)
            print(f"Intraday script: {sym} → context/{sym.lower()}_data.md")

    prior_section = ""
    prior_source = ""
    if prior_final and prior_final.exists():
        prior_text = prior_final.read_text(encoding="utf-8").strip()
        prior_section = prior_text[:12000]
        if len(prior_text) > 12000:
            prior_section += "\n\n...(昨日盘后报告截断)...\n"
        prior_source = str(prior_final.relative_to(ROOT))
        print(f"Prior after-hours report: {prior_source}")

    lines = [
        "# Market Context — Daily (14:30)",
        "",
        f"## 采集时间\n{now_local} UTC+8 参考",
        "",
        f"## 当前日期\n{today}",
        "",
        f"## 议题\n{state.get('topic', '')}",
        "",
        f"## 范围\n{scope}",
        "",
    ]
    if prior_section:
        lines.extend(["## 昨日盘后分析（只读引用）", f"来源：`{prior_source}`", "", prior_section, ""])
    if equity_blocks:
        lines.extend(["## 今日白天脚本数据（实时）", *equity_blocks, ""])
    else:
        lines.extend(["## 今日白天脚本数据", "数据缺失：未识别到可抓取标的", ""])

    used_mock = False
    if not skip_llm:
        guests = load_guests()
        collector = guests.get("context_collector", guests.get("nemo", {}))
        prompt = (
            f"整理以下日频 context，只引用已有数据，禁止联网检索。\n范围：{scope}\n\n"
            + "\n".join(lines)
        )
        body, used_mock = invoke_cli(
            collector.get("command", ""),
            prompt,
            mock_label="context-collector",
            round_num=state.get("round", 0),
            guest="context",
            kind="guest",
            timeout_seconds=int(collector.get("timeout_seconds", 60)),
        )
        if not used_mock and body.strip():
            lines = [strip_markdown_fences(body)]

    body_md = "\n".join(lines).strip() + "\n"
    context_dir = meeting_dir / "context"
    md_path, manifest_path, _json_path = ContextPack.write(
        context_dir,
        body=body_md,
        scope=scope,
        topic=state.get("topic", ""),
        generated_at=utc_now(),
        metadata={
            "date": today,
            "mode": "daily",
            "skip_llm": skip_llm,
            "used_mock": used_mock,
            "prior_final": prior_source,
            "equity_feeds": equity_meta,
        },
    )
    return {
        "md_path": md_path,
        "manifest_path": manifest_path,
        "used_mock": used_mock,
        "equity_feeds": equity_meta,
    }


def generate_daily_decision_md(state: dict[str, Any], meeting_dir: Path, round_num: int) -> str:
    """从本轮 guest raw + state 生成基金决策草案。"""
    tag = round_tag(round_num)
    guest_blocks: list[str] = []
    for path in sorted((meeting_dir / "raw").glob(f"round-{tag}-*.md")):
        guest = path.stem.replace(f"round-{tag}-", "")
        text = path.read_text(encoding="utf-8").strip()
        judgment = ""
        m = re.search(r"判断[：:]\s*\n(.+?)(?=\n\n|\n已确认事实)", text, re.S)
        if m:
            judgment = m.group(1).strip()[:400]
        guest_blocks.append(f"### {guest}\n{judgment or text[:500]}")

    cp = format_list(filter_semantic_items(state.get("confirmed_points", []))[-8:])
    cf = format_list(filter_semantic_items(state.get("conflicts", []))[-5:])
    oq = format_list(filter_semantic_items(state.get("open_questions", []))[-5:])

    return "\n".join(
        [
            f"# 基金操作建议 — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            f"**会议：** {state.get('meeting_id', '')} | **Round：** {tag}",
            "",
            "## 结论草案",
            "",
            "> Owner 确认后执行。以下为多模型合议摘要，非投资建议。",
            "",
            state.get("guest_summaries", {}).get("qoder")
            or state.get("guest_summaries", {}).get("codex")
            or state.get("guest_summaries", {}).get("laguna")
            or "（见下方各 Guest 判断）",
            "",
            "## 各 Guest 判断",
            "",
            *guest_blocks,
            "",
            "## 已确认事实（state）",
            cp,
            "",
            "## 分歧",
            cf,
            "",
            "## 未决问题",
            oq,
            "",
            "## 失效条件（来自 codex/qoder，请人工复核）",
            "- 见各 guest raw 中 claim_responses 与可证伪价位",
            "",
        ]
    ) + "\n"

