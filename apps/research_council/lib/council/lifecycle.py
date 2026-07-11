"""Council: lifecycle."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from council.metrics import compute_metrics, metrics_markdown
from council.reports.generators import (
    generate_council_experiment_report,
    generate_council_investment_report,
    generate_enhanced_final_md,
)
from missionos.utils import utc_now

from council.cli_runner import invoke_cli
from council.config import INVESTMENT_REPORT_PROMPT
from council.formatting import format_guest_summaries, format_list, render_template, round_tag
from council.guests import is_investment_mode, is_json_mode, is_research_mode, load_guests
from council.state_store import load_state, save_state


def build_meeting_materials(state: dict[str, Any], meeting_dir: Path) -> str:
    parts = [
        f"# Topic\n{state.get('topic', '')}",
        f"\n# Owner Question\n{state.get('owner_question', '')}",
        f"\n# Output Format\n{state.get('output_format', 'json')}",
        f"\n# Total Rounds\n{state.get('round', 0)}",
        f"\n# Stop Reason\n{state.get('stop_reason', '')}",
    ]
    if is_json_mode(state):
        parts.append("\n# Positions (latest per guest)\n" + json.dumps(state.get("positions", {}), ensure_ascii=False, indent=2))
        parts.append("\n# Challenges\n" + json.dumps(state.get("challenges", []), ensure_ascii=False, indent=2))
        parts.append("\n# Verifications\n" + format_list(state.get("verifications", [])))
        parts.append("\n# Round Records\n" + json.dumps(state.get("round_records", []), ensure_ascii=False, indent=2))
    else:
        parts.extend(
            [
                "\n# Confirmed Points\n" + format_list(state.get("confirmed_points", [])),
                "\n# Conflicts\n" + format_list(state.get("conflicts", [])),
                "\n# Open Questions\n" + format_list(state.get("open_questions", [])),
                "\n# Guest Summaries\n" + format_guest_summaries(state.get("guest_summaries", {})),
            ]
        )
    for h in state.get("history", []):
        rel = h.get("json_path") or h.get("raw_output_path")
        if not rel:
            continue
        raw_path = meeting_dir / rel
        if raw_path.exists():
            raw = raw_path.read_text(encoding="utf-8")
            excerpt = raw[:2500] + ("\n...(truncated)" if len(raw) > 2500 else "")
            parts.append(f"\n## Record — Round {h['round']} / {h['guest']}\n{excerpt}")
    return "\n".join(parts)


def generate_investment_report(state: dict[str, Any], meeting_dir: Path, guests: dict[str, Any]) -> str:
    materials = build_meeting_materials(state, meeting_dir)
    if INVESTMENT_REPORT_PROMPT.exists():
        prompt = render_template(INVESTMENT_REPORT_PROMPT, {"meeting_materials": materials})
        reporter = guests.get("reporter", guests.get("qwen", {}))
        cmd = reporter.get("command", "")
        body, used_mock = invoke_cli(
            cmd,
            prompt,
            mock_label="report-writer",
            round_num=state.get("round", 0),
            guest="report",
            kind="guest",
        )
        if not used_mock and body.strip():
            return body.strip() + "\n"

    lines = [
        "# 全球宏观投资委员会实验报告",
        "",
        f"**会议 ID:** {state['meeting_id']}",
        f"**终止原因:** {state.get('stop_reason', 'manual')}",
        f"**总轮次:** {state.get('round', 0)}",
        "",
        "## 1. 执行摘要",
        "基于委员讨论材料自动汇编，详见下文与 raw 审计文件。",
        "",
        "## 2. 过去两周市场背景",
        format_list([cp for cp in state.get("confirmed_points", [])][:8]),
        "",
        "## 7. 主要分歧",
        format_list(state.get("conflicts", [])),
        "",
        "## 8. 关键风险",
        format_list(state.get("open_questions", [])),
        "",
        "## 12. 最不确定的判断",
        format_list(state.get("open_questions", [])[-5:]),
        "",
        "## 14. 各委员核心观点引用",
        format_guest_summaries(state.get("guest_summaries", {})),
        "",
        "## 15. 免责声明",
        "本报告为多模型投资委员会实验输出，不构成投资建议。请 Owner 人工复核关键数据点。",
    ]
    return "\n".join(lines) + "\n"


def finish_meeting(meeting_dir: Path, stop_reason: str = "manual") -> None:
    state = load_state(meeting_dir)
    guests = load_guests()
    state["status"] = "stopped"
    state["owner_required"] = False
    state["stop_reason"] = stop_reason
    save_state(meeting_dir, state)

    metrics = compute_metrics(meeting_dir, state, load_guests())
    (meeting_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (meeting_dir / "metrics.md").write_text(metrics_markdown(metrics), encoding="utf-8")

    final_path = meeting_dir / "final.md"
    has_parallel = any(h.get("mode") == "parallel" for h in state.get("history", []))
    if is_research_mode(state) or has_parallel:
        final_path.write_text(generate_enhanced_final_md(state, meeting_dir, metrics), encoding="utf-8")
    else:
        final_path.write_text(generate_final_md(state, meeting_dir), encoding="utf-8")

    if is_investment_mode(state):
        report_path = meeting_dir / "investment_report.md"
        report_path.write_text(generate_investment_report(state, meeting_dir, guests), encoding="utf-8")
        print(f"Investment report: {report_path}")
    elif is_research_mode(state) or has_parallel:
        inv_path = meeting_dir / "investment_report.md"
        exp_path = meeting_dir / "council_experiment_report.md"
        inv_path.write_text(generate_council_investment_report(state, meeting_dir, metrics), encoding="utf-8")
        exp_path.write_text(generate_council_experiment_report(state, metrics), encoding="utf-8")
        print(f"Investment report: {inv_path}")
        print(f"Experiment report: {exp_path}")

    print(f"Meeting stopped: {state['meeting_id']}")
    print(f"Final report: {final_path}")
    print(f"Stop reason: {stop_reason}")


def generate_final_md(state: dict[str, Any], meeting_dir: Path) -> str:
    lines = [
        f"# Council Final — {state['meeting_id']}",
        "",
        f"**Topic:** {state['topic']}",
        f"**Owner Question:** {state['owner_question']}",
        f"**Status:** stopped",
        f"**Total Rounds:** {state['round']}",
        f"**Stopped At:** {utc_now()}",
        "",
        "## Confirmed Points",
        format_list(state.get("confirmed_points", [])),
        "",
        "## Conflicts",
        format_list(state.get("conflicts", [])),
        "",
        "## Open Questions",
        format_list(state.get("open_questions", [])),
        "",
        "## Owner Views",
        format_list(state.get("owner_views", []), empty="(无)"),
        "",
        "## Guest Summaries",
        format_guest_summaries(state.get("guest_summaries", {})),
        "",
        "## Round History",
    ]
    for h in state.get("history", []):
        lines.append(
            f"- Round {round_tag(h['round'])} / {h['guest']}: "
            f"raw=`{h['raw_output_path']}` summary=`{h['summary_path']}`"
        )
    lines.append("")
    lines.append("## Audit Note")
    lines.append("Raw files are evidence. Summaries are projections. Re-summarize from raw if needed.")
    return "\n".join(lines) + "\n"

