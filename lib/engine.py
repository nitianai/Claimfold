#!/usr/bin/env python3
"""Council Engine V0.1 — deterministic multi-model meeting workflow runtime."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from claim_lifecycle import (
    append_event,
    compute_fingerprint,
    ensure_claims_dir,
    format_prior_claims_for_prompt,
    load_index,
    next_claim_id,
    parse_claim_responses_from_raw,
    rebuild_index,
    select_claims_for_injection,
    validate_injection_text,
    validate_promotion_candidate,
    validate_scope,
    verify_three_meeting_chain,
)
from runtime_ext import (
    apply_summary_json_to_state,
    artifact_paths_research,
    build_summary_json,
    compute_metrics,
    generate_council_experiment_report,
    generate_council_investment_report,
    generate_enhanced_final_md,
    load_full_config,
    max_parallel_from_config,
    metrics_markdown,
    read_market_context,
    resolve_guest_alias,
    select_guests_for_focus,
    summary_json_to_md,
    verify_research_semantic_loop,
)

ROOT = Path(__file__).resolve().parent.parent
CURRENT_MEETING_FILE = ROOT / ".current_meeting"
CONFIG_FILE = ROOT / "config" / "guests.yaml"
GUEST_TEMPLATE = ROOT / "prompts" / "guest" / "template.md"
GUEST_JSON_TEMPLATE = ROOT / "prompts" / "guest" / "json.md"
GUEST_RESEARCH_TEMPLATE = ROOT / "prompts" / "guest" / "research.md"
INVESTMENT_GUEST_TEMPLATE = ROOT / "prompts" / "guest" / "investment.md"
SUMMARIZER_TEMPLATE = ROOT / "prompts" / "system" / "summarizer.md"
MARKET_CONTEXT_PROMPT = ROOT / "prompts" / "system" / "market_context.md"
INVESTMENT_REPORT_PROMPT = ROOT / "prompts" / "reports" / "investment_report.md"
MEETINGS_DIR = ROOT / "meetings"

INVESTMENT_AGENDA: list[dict[str, str]] = [
    {
        "guest": "qwen",
        "question": (
            "【Round 1】请梳理过去两周（截至2026年7月9日）全球主要金融市场走势："
            "美股、A股、港股、黄金、原油、美债、美元指数、人民币汇率。"
            "只列已确认事实与数据来源，区分事实/推断/预期。"
        ),
    },
    {
        "guest": "laguna",
        "question": (
            "【Round 2】基于过去两周信息，当前核心宏观驱动是什么？"
            "覆盖：主要经济体数据、央行政策（Fed/ECB/PBOC）、地缘政治、财政政策。"
            "哪些是指定价锚，哪些是尾部风险？"
        ),
    },
    {
        "guest": "north",
        "question": (
            "【Round 3】黄金与原油：过去两周走势、当前定价逻辑、未来一周三种可能路径。"
            "引用库存/期货曲线/地缘溢价/美元与实际利率等证据。"
        ),
    },
    {
        "guest": "mimo",
        "question": (
            "【Round 4】美股、A股、港股及重点行业板块：过去两周表现、盈利与估值、资金面。"
            "科技/能源/金融/消费/国防等行业相对强弱，未来一周行业轮动判断。"
        ),
    },
    {
        "guest": "nemo",
        "question": (
            "【Round 5】美债收益率曲线、美元指数、人民币汇率、跨境资金流向："
            "过去两周变化与未来一周定价逻辑。区分已确认事实与市场预期。"
        ),
    },
    {
        "guest": "qwen",
        "question": (
            "【Round 6 — Scenario A】构建**基准情景**（未来一周最可能路径）："
            "情景名称、概率区间、触发条件、证据、反证、受益/受损资产、"
            "对美股/A股/港股/黄金/原油/美债/美元/人民币的影响、验证事件。"
        ),
    },
    {
        "guest": "laguna",
        "question": (
            "【Round 7 — Scenario B】构建**风险升级情景**（地缘/通胀/政策超预期）："
            "完整 Scenario 格式。挑战 Scenario A 的哪些假设？"
        ),
    },
    {
        "guest": "north",
        "question": (
            "【Round 8 — Scenario C】构建**缓解/反转情景**（冲突降温/数据走弱/政策转鸽）："
            "完整 Scenario 格式。与 A/B 的关键差异是什么？"
        ),
    },
    {
        "guest": "mimo",
        "question": (
            "【Round 9】在三种情景下，对比美股/A股/港股/重点行业的相对表现与仓位含义。"
            "不要求统一观点，列明分歧。"
        ),
    },
    {
        "guest": "nemo",
        "question": (
            "【Round 10】给出未来一周**资产配置百分比建议**（合计100%）："
            "现金、美股、A股、港股、黄金、美债、原油/能源、美元/外汇。"
            "附仓位建议与关键风险。"
        ),
    },
]

INVESTMENT_REFINE_QUESTIONS = [
    "【深化】针对当前最大分歧，请用最新公开数据补充证据或反证。",
    "【验证】请列出下周必须跟踪的3个关键事件/数据及其对三情景概率的影响。",
    "【复核】请标注哪些数据点需要 Owner 人工复核，并说明原因。",
    "【收敛】三情景概率是否应调整？请给出修正及理由，保留不同意见。",
    "【风险】当前市场定价忽略了哪些尾部风险？",
]

SECTION_KEYS = (
    "confirmed_points",
    "conflicts",
    "open_questions",
    "guest_position_summary",
    "suggested_next_question",
)

SECTION_ALIASES = {
    "confirmed_points": "confirmed_points",
    "confirmed points": "confirmed_points",
    "conflicts": "conflicts",
    "open_questions": "open_questions",
    "open questions": "open_questions",
    "guest_position_summary": "guest_position_summary",
    "guest position summary": "guest_position_summary",
    "suggested_next_question": "suggested_next_question",
    "suggested next question": "suggested_next_question",
}

LEGACY_GUEST_MAP = {
    "claude": "qwen",
    "grok": "laguna",
    "codex": "north",
    "nemotron": "nemo",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_guests() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        raise SystemExit(f"Config not found: {CONFIG_FILE}. Run: ./council.sh init")
    with CONFIG_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("guests", {})


def guest_roster(guests: dict[str, Any]) -> list[str]:
    skip = {"summarizer", "reporter"}
    return [
        name
        for name, cfg in guests.items()
        if name not in skip and not cfg.get("reporter") and not cfg.get("summarizer") and cfg.get("enabled", True)
    ]


def is_json_mode(state: dict[str, Any]) -> bool:
    return state.get("output_format", "json") == "json"


def is_research_mode(state: dict[str, Any]) -> bool:
    return state.get("output_format") == "research" or state.get("round_mode") == "parallel"


def guest_role_id(guests: dict[str, Any], guest_name: str) -> str:
    return guests.get(guest_name, {}).get("role_id", guest_name)


def load_state(meeting_dir: Path) -> dict[str, Any]:
    path = meeting_dir / "meeting_state.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_state(meeting_dir: Path, state: dict[str, Any]) -> None:
    path = meeting_dir / "meeting_state.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_current_meeting_dir() -> Path:
    if not CURRENT_MEETING_FILE.exists():
        raise SystemExit("No active meeting. Run: ./council.sh start \"议题\"")
    meeting_id = CURRENT_MEETING_FILE.read_text(encoding="utf-8").strip()
    meeting_dir = MEETINGS_DIR / meeting_id
    if not meeting_dir.exists():
        raise SystemExit(f"Meeting directory missing: {meeting_dir}")
    return meeting_dir


def format_list(items: list[str], empty: str = "(无)") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def format_guest_summaries(summaries: dict[str, str]) -> str:
    if not summaries:
        return "(无)"
    lines = []
    for guest, summary in summaries.items():
        lines.append(f"### {guest}")
        lines.append(summary.strip() or "(空)")
    return "\n".join(lines)


def render_template(template_path: Path, variables: dict[str, str]) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def round_tag(n: int) -> str:
    return f"{n:03d}"


def artifact_paths(meeting_dir: Path, round_num: int, guest: str, *, json_mode: bool = True) -> dict[str, Path]:
    tag = round_tag(round_num)
    paths = {
        "prompt": meeting_dir / "prompts" / f"round-{tag}-{guest}.prompt.md",
        "raw": meeting_dir / "raw" / f"round-{tag}-{guest}.{'json' if json_mode else 'md'}",
    }
    if not json_mode:
        paths["summary"] = meeting_dir / "summaries" / f"round-{tag}-{guest}.summary.md"
    return paths


def command_available(command: str) -> bool:
    if not command or not command.strip():
        return False
    parts = shlex.split(command)
    if not parts:
        return False
    return shutil.which(parts[0]) is not None


def mock_mode_enabled() -> bool:
    return os.environ.get("COUNCIL_MOCK", "").strip().lower() in ("1", "true", "yes")


def invoke_cli(
    command: str,
    prompt: str,
    *,
    mock_label: str,
    round_num: int,
    guest: str,
    kind: str,
    timeout_seconds: int = 600,
) -> tuple[str, bool]:
    """Run guest/summarizer CLI. Returns (output, used_mock)."""
    if mock_mode_enabled() or not command_available(command):
        label = mock_label if not mock_mode_enabled() else "forced-mock"
        return generate_mock_output(kind=kind, guest=guest, round_num=round_num, label=label), True

    parts = shlex.split(command)
    try:
        result = subprocess.run(
            parts,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            return (
                generate_mock_output(
                    kind=kind,
                    guest=guest,
                    round_num=round_num,
                    label=f"{mock_label} (CLI failed: {stderr[:200]})",
                ),
                True,
            )
        output = (result.stdout or "").strip()
        if not output:
            return generate_mock_output(kind=kind, guest=guest, round_num=round_num, label=mock_label), True
        return output, False
    except (subprocess.TimeoutExpired, OSError) as exc:
        return (
            generate_mock_output(
                kind=kind,
                guest=guest,
                round_num=round_num,
                label=f"{mock_label} (error: {exc})",
            ),
            True,
        )


def extract_json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in guest output")
    return json.loads(text[start : end + 1])


def validate_guest_json(data: dict[str, Any], *, guest_name: str, role_id: str, round_num: int) -> list[str]:
    errors: list[str] = []
    required = (
        "speaker",
        "role",
        "round",
        "focus",
        "position",
        "confidence",
        "evidence",
        "risks",
        "challenge_to",
        "challenge_question",
        "need_verification",
    )
    for key in required:
        if key not in data:
            errors.append(f"missing field: {key}")

    if data.get("speaker") != guest_name:
        errors.append(f"speaker must be {guest_name}")
    if data.get("role") != role_id:
        errors.append(f"role must be {role_id}")
    if data.get("round") != round_num:
        errors.append(f"round must be {round_num}")

    position = str(data.get("position", ""))
    if len(position) > 50:
        errors.append(f"position exceeds 50 chars ({len(position)})")

    if not isinstance(data.get("confidence"), int) or not (0 <= int(data["confidence"]) <= 100):
        errors.append("confidence must be integer 0-100")

    for field, max_items in (("evidence", 3), ("risks", 2), ("need_verification", 99)):
        val = data.get(field, [])
        if not isinstance(val, list):
            errors.append(f"{field} must be a list")
        elif field != "need_verification" and len(val) > max_items:
            errors.append(f"{field} exceeds max {max_items} items")

    return errors


def format_peer_positions(state: dict[str, Any], guest_name: str) -> str:
    positions = state.get("positions", {})
    if not positions:
        return "(无)"
    lines = []
    for speaker, record in positions.items():
        if speaker == guest_name:
            continue
        lines.append(
            f"- {speaker} ({record.get('role', '')}): "
            f"{record.get('position', '')} [confidence={record.get('confidence', '?')}]"
        )
    return "\n".join(lines) if lines else "(无)"


def merge_guest_json_into_state(state: dict[str, Any], data: dict[str, Any]) -> dict[str, int]:
    speaker = data["speaker"]
    before_verifications = len(state.setdefault("verifications", []))
    before_challenges = len(state.setdefault("challenges", []))
    old_position = state.setdefault("positions", {}).get(speaker, {}).get("position", "")

    state["positions"][speaker] = data
    state.setdefault("round_records", []).append(data)

    for item in data.get("evidence", []):
        if item and item not in state.setdefault("confirmed_points", []):
            state["confirmed_points"].append(f"[{speaker}] {item}")

    for item in data.get("risks", []):
        if item and item not in state.setdefault("conflicts", []):
            state["conflicts"].append(f"[{speaker}] risk: {item}")

    for item in data.get("need_verification", []):
        if item and item not in state["verifications"]:
            state["verifications"].append(item)
            if item not in state.setdefault("open_questions", []):
                state["open_questions"].append(item)

    if data.get("challenge_to") and data.get("challenge_question"):
        challenge = {
            "speaker": speaker,
            "challenge_to": data["challenge_to"],
            "challenge_question": data["challenge_question"],
            "round": data.get("round"),
        }
        state["challenges"].append(challenge)

    state.setdefault("guest_summaries", {})[speaker] = data.get("position", "")

    items_added = 0
    if data.get("position") != old_position:
        items_added += 1
    items_added += len(state["verifications"]) - before_verifications
    items_added += len(state["challenges"]) - before_challenges

    return {"items_added": items_added}


def generate_mock_guest_json(*, guest: str, role_id: str, round_num: int, focus: str, label: str) -> str:
    payload = {
        "speaker": guest,
        "role": role_id,
        "round": round_num,
        "focus": focus[:80] if focus else "unknown",
        "position": f"[MOCK/{label}] 第{round_num}轮模拟立场，待接入真实CLI",
        "confidence": 50,
        "evidence": [
            f"模拟证据A round {round_tag(round_num)}",
            "模拟证据B",
        ],
        "risks": ["CLI不可用", "数据待复核"],
        "challenge_to": "",
        "challenge_question": "",
        "need_verification": ["接入真实模型后重跑"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def generate_mock_research_output(
    *,
    guest: str,
    round_num: int,
    label: str,
    state: dict[str, Any],
    injected_claims: list[dict[str, Any]] | None = None,
) -> str:
    """Mock guest output that satisfies semantic loop obligations when prior state exists."""
    conflicts = state.get("conflicts", [])
    confirmed = state.get("confirmed_points", [])
    open_q = state.get("open_questions", [])

    response_lines: list[str] = []
    if conflicts:
        target = conflicts[0]
        response_lines.append(
            f"反方视角：\n- [回应 conflict] {guest} 针对分歧「{target}」：部分同意前提，但认为证据不足，建议用 market_context 复核。"
        )
    if open_q:
        target = open_q[0]
        response_lines.append(
            f"判断：\n- [细化 open_question] 关于「{target}」：{guest} 认为需补充数据源后方可关闭，暂列验证清单。"
        )
    if confirmed and not conflicts:
        target = confirmed[0]
        response_lines.append(
            f"判断：\n- [修正 confirmed_point] 对「{target}」：{guest} 补充时间维度，立场不变但置信度下调。"
        )

    if not response_lines:
        response_lines.append(
            f"判断：\n[MOCK/{label}] Round {round_tag(round_num)} — {guest} 首轮发言，建立基线观点。"
        )

    body = "\n\n".join(response_lines)
    claim_block = ""
    if injected_claims:
        target = injected_claims[0]
        cid = target.get("claim_id", "clm-000001")
        claim_block = f"""
claim_responses:
- claim_id: {cid} | response: CHALLENGE | statement: [MOCK/{label}] {guest} 指出美元走强阶段该命题适用边界过宽
"""
    return f"""{body}

证据：
- 模拟证据 A（可审计测试数据）
- 模拟证据 B
{claim_block}
风险：
- 模拟风险：命令不可用，当前为 mock 模式

建议：
- 接入真实 CLI 后重新运行该轮

是否需要下一轮：
是
"""


def generate_mock_output(*, kind: str, guest: str, round_num: int, label: str, role_id: str = "", focus: str = "") -> str:
    if kind == "guest":
        if role_id:
            return generate_mock_guest_json(
                guest=guest, role_id=role_id, round_num=round_num, focus=focus, label=label
            )
        return f"""判断：
[MOCK/{label}] Round {round_tag(round_num)} — {guest} 的模拟发言。

证据：
- 模拟证据 A（可审计测试数据）
- 模拟证据 B

反方视角：
- 模拟反方：需验证假设是否成立

风险：
- 模拟风险：命令不可用，当前为 mock 模式

建议：
- 接入真实 CLI 后重新运行该轮

是否需要下一轮：
是
"""
    return f"""## confirmed_points
- [MOCK/{label}] {guest} 在 round {round_tag(round_num)} 提出可测试观点

## conflicts
- [MOCK] 与既有方案存在待验证分歧

## open_questions
- 真实 CLI 接入后是否复现相同结构？

## guest_position_summary
{guest}（round {round_tag(round_num)}）倾向先验证最小可行路径。

## suggested_next_question
下一步应优先验证哪条假设？
"""


def parse_summary_sections(text: str) -> dict[str, Any]:
    text = prepare_summary_text(text)
    sections: dict[str, Any] = {
        "confirmed_points": [],
        "conflicts": [],
        "open_questions": [],
        "guest_position_summary": "",
        "suggested_next_question": "",
    }
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current, buffer
        if current is None:
            return
        content = "\n".join(buffer).strip()
        if current in ("confirmed_points", "conflicts", "open_questions"):
            sections[current] = split_list_items(content)
        else:
            sections[current] = content
        buffer = []

    def set_field(field: str, inline: str = "") -> None:
        nonlocal current
        flush()
        current = field
        if inline.strip():
            buffer.append(inline.strip())

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped in ("---", "|||"):
            continue
        if re.match(r"^\|[-\s|:]+\|$", stripped):
            continue

        field: str | None = None
        inline = ""

        table = re.match(r"^\|\s*\*?\*?(.+?)\*?\*?\s*\|\s*(.+?)\s*\|?\s*$", stripped)
        if table:
            field = normalize_section_name(table.group(1))
            inline = table.group(2).strip()
            if field:
                set_field(field, inline)
                flush()
                current = None
                continue

        for pattern in (
            r"^#+\s*(.+?)\s*$",
            r"^\*\*(.+?)\*\*\s*$",
            r"^[-*•]?\s*\*\*(.+?)\*\*\s*:?\s*(.*)$",
            r"^(\d+)\.\s*(.+?)\s*:?\s*(.*)$",
            r"^[-*•]?\s*(confirmed_points|conflicts|open_questions|guest_position_summary|suggested_next_question)\s*:?\s*(.*)$",
        ):
            match = re.match(pattern, stripped, re.I)
            if not match:
                continue
            if pattern.startswith(r"^(\d+)"):
                field = normalize_section_name(match.group(2))
                inline = match.group(3)
            elif "confirmed_points|" in pattern:
                field = normalize_section_name(match.group(1))
                inline = match.group(2)
            else:
                field = normalize_section_name(match.group(1))
                inline = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
            if field:
                break

        if field:
            set_field(field, inline)
            continue

        if current is not None:
            buffer.append(line)

    flush()
    return sections


def apply_parsed_summary(state: dict[str, Any], guest_name: str, parsed: dict[str, Any]) -> dict[str, int]:
    cp_before = len(state["confirmed_points"])
    cf_before = len(state["conflicts"])
    oq_before = len(state["open_questions"])

    state["confirmed_points"] = merge_unique(state["confirmed_points"], parsed["confirmed_points"])
    state["conflicts"] = merge_unique(state["conflicts"], parsed["conflicts"])
    state["open_questions"] = merge_unique(state["open_questions"], parsed["open_questions"])
    if parsed["guest_position_summary"]:
        state["guest_summaries"][guest_name] = parsed["guest_position_summary"]

    return {
        "confirmed_points_added": len(state["confirmed_points"]) - cp_before,
        "conflicts_added": len(state["conflicts"]) - cf_before,
        "open_questions_added": len(state["open_questions"]) - oq_before,
    }


def rebuild_state_from_summaries(state: dict[str, Any], meeting_dir: Path) -> None:
    last_question = state.get("owner_question", "")
    state["confirmed_points"] = []
    state["conflicts"] = []
    state["open_questions"] = []
    state["guest_summaries"] = {}

    for entry in state.get("history", []):
        summary_path = meeting_dir / entry["summary_path"]
        if not summary_path.exists():
            continue
        guest = entry["guest"]
        parsed = parse_summary_sections(summary_path.read_text(encoding="utf-8"))
        counts = apply_parsed_summary(state, guest, parsed)
        entry["confirmed_points_added"] = counts["confirmed_points_added"]
        entry["conflicts_added"] = counts["conflicts_added"]
        entry["open_questions_added"] = counts["open_questions_added"]
        if parsed["suggested_next_question"]:
            last_question = parsed["suggested_next_question"]

    state["next_question"] = last_question


def migrate_guest_names(meeting_dir: Path, state: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    for sub in ("prompts", "raw", "summaries"):
        folder = meeting_dir / sub
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            name = path.name
            for old, new in LEGACY_GUEST_MAP.items():
                token = f"-{old}."
                if token not in name:
                    continue
                target = path.with_name(name.replace(token, f"-{new}."))
                if target.exists() and target != path:
                    continue
                path.rename(target)
                changes.append(f"{path.relative_to(meeting_dir)} -> {target.relative_to(meeting_dir)}")
                if sub == "summaries":
                    text = target.read_text(encoding="utf-8")
                    text = re.sub(rf"^guest:\s*{re.escape(old)}\s*$", f"guest: {new}", text, flags=re.M)
                    text = text.replace(f"../raw/round-", f"../raw/round-").replace(
                        f"-{old}.md", f"-{new}.md"
                    )
                    target.write_text(text, encoding="utf-8")
                break

    def remap_guest(name: str) -> str:
        return LEGACY_GUEST_MAP.get(name, name)

    if state.get("next_speaker"):
        state["next_speaker"] = remap_guest(state["next_speaker"])

    new_summaries: dict[str, str] = {}
    for guest, summary in state.get("guest_summaries", {}).items():
        new_summaries[remap_guest(guest)] = summary
    state["guest_summaries"] = new_summaries

    for entry in state.get("history", []):
        old_guest = entry["guest"]
        new_guest = remap_guest(old_guest)
        entry["guest"] = new_guest
        for key in ("prompt_path", "raw_output_path", "summary_path"):
            if key in entry:
                for old, new in LEGACY_GUEST_MAP.items():
                    entry[key] = entry[key].replace(f"-{old}.", f"-{new}.")

    return changes


def merge_unique(existing: list[str], new_items: list[str]) -> list[str]:
    seen = set(existing)
    out = list(existing)
    for item in new_items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def is_investment_mode(state: dict[str, Any]) -> bool:
    return state.get("meeting_mode") == "investment"


def guest_template_path(state: dict[str, Any]) -> Path:
    if is_research_mode(state) and GUEST_RESEARCH_TEMPLATE.exists():
        return GUEST_RESEARCH_TEMPLATE
    if is_json_mode(state) and GUEST_JSON_TEMPLATE.exists():
        return GUEST_JSON_TEMPLATE
    if is_investment_mode(state) and INVESTMENT_GUEST_TEMPLATE.exists():
        return INVESTMENT_GUEST_TEMPLATE
    return GUEST_TEMPLATE


def resolve_round_question(state: dict[str, Any], round_num: int, guest_name: str) -> str:
    if is_investment_mode(state):
        agenda = state.get("round_agenda") or INVESTMENT_AGENDA
        if round_num <= len(agenda):
            return agenda[round_num - 1]["question"]
        refine_idx = (round_num - len(agenda) - 1) % len(INVESTMENT_REFINE_QUESTIONS)
        return INVESTMENT_REFINE_QUESTIONS[refine_idx] + f"（当前委员：{guest_name}）"
    return state.get("next_question") or state.get("owner_question") or state.get("topic", "")


def check_investment_auto_stop(state: dict[str, Any]) -> str | None:
    if not is_investment_mode(state):
        return None
    current_round = state.get("round", 0)
    max_rounds = state.get("max_rounds", 100)
    if current_round >= max_rounds:
        return f"已达最大轮次 {max_rounds}"

    history = state.get("history", [])
    stale_limit = state.get("stale_round_limit", 5)
    if len(history) >= stale_limit:
        last_n = history[-stale_limit:]
        if is_json_mode(state):
            stale = all(h.get("items_added", 0) == 0 for h in last_n)
        else:
            stale = all(
                h.get("confirmed_points_added", 0) == 0
                and h.get("conflicts_added", 0) == 0
                and h.get("open_questions_added", 0) == 0
                for h in last_n
            )
        if stale:
            return f"连续 {stale_limit} 轮无新增 confirmed/conflicts/open_questions"

    if current_round >= 10 and len(history) >= 3:
        last_3 = history[-3:]
        no_new_conflicts = all(h.get("conflicts_added", 0) == 0 for h in last_3)
        scenario_hits = sum(
            1 for cp in state.get("confirmed_points", []) if "情景" in cp or "Scenario" in cp
        )
        if no_new_conflicts and scenario_hits >= 2:
            return "主要分歧已明确且连续3轮无新冲突，形成稳定讨论终点"

    return None


def build_prompt_context(
    state: dict[str, Any], guests: dict[str, Any], guest_name: str, round_num: int = 0
) -> dict[str, str]:
    question = state.get("next_question") or state.get("owner_question") or state.get("topic", "")
    if is_json_mode(state):
        role_id = guest_role_id(guests, guest_name)
        incoming = []
        for c in state.get("challenges", []):
            target = c.get("challenge_to", "")
            if target in (guest_name, role_id):
                incoming.append(f"- from {c.get('speaker')}: {c.get('challenge_question')}")
        return {
            "topic": state.get("topic", ""),
            "next_question": question,
            "guest_id": guest_name,
            "role_id": role_id,
            "round_num": str(round_num),
            "peer_positions": format_peer_positions(state, guest_name),
            "incoming_challenges": "\n".join(incoming) if incoming else "(无)",
        }
    return {
        "topic": state.get("topic", ""),
        "owner_question": state.get("owner_question", ""),
        "confirmed_points": format_list(state.get("confirmed_points", [])),
        "conflicts": format_list(state.get("conflicts", [])),
        "open_questions": format_list(state.get("open_questions", [])),
        "owner_views": format_list(state.get("owner_views", []), empty="(无)"),
        "guest_summaries": format_guest_summaries(state.get("guest_summaries", {})),
        "guest_role": guests.get(guest_name, {}).get("role", guest_name),
        "next_question": question,
    }


def next_guest_name(state: dict[str, Any], roster: list[str]) -> str:
    if state.get("next_speaker") and state["next_speaker"] in roster:
        return state["next_speaker"]
    return roster[0] if roster else ""


def rotate_guest(current: str, roster: list[str]) -> str:
    if not roster:
        return ""
    if current not in roster:
        return roster[0]
    idx = roster.index(current)
    return roster[(idx + 1) % len(roster)]


def ensure_no_overwrite(path: Path) -> None:
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing artifact: {path}")


def write_summary_file(
    path: Path,
    *,
    meeting_id: str,
    round_num: int,
    guest: str,
    body: str,
) -> None:
    raw_rel = f"../raw/round-{round_tag(round_num)}-{guest}.md"
    frontmatter = (
        "---\n"
        f"meeting_id: {meeting_id}\n"
        f"round: {round_num}\n"
        f"guest: {guest}\n"
        f"source: {raw_rel}\n"
        "summary_type: compressed\n"
        "---\n\n"
    )
    path.write_text(frontmatter + body.strip() + "\n", encoding="utf-8")


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3 :].lstrip("\n")
    return text


def prepare_summary_text(text: str) -> str:
    text = strip_frontmatter(text)
    text = text.strip()
    text = re.sub(r"^```(?:markdown|md)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def normalize_section_name(raw: str) -> str | None:
    clean = re.sub(r"[*#`|]", "", raw).strip().lower()
    clean = re.sub(r"\s+", " ", clean).rstrip(":").strip()
    if clean in SECTION_ALIASES:
        return SECTION_ALIASES[clean]
    snake = clean.replace(" ", "_")
    if snake in SECTION_KEYS:
        return snake
    return None


def split_list_items(content: str) -> list[str]:
    items: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or re.match(r"^\|[-\s|]+\|$", line):
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[1]:
                line = cells[1]
            else:
                continue
        line = re.sub(r"^[-*•]\s*", "", line)
        line = re.sub(r"^\d+\.\s*", "", line)
        line = re.sub(r"^\*\*(.+?)\*\*:?\s*", "", line).strip()
        if line:
            items.append(line)
    if not items and content.strip():
        inline = content.strip()
        if "|" in inline:
            cells = [c.strip() for c in inline.strip("|").split("|")]
            if len(cells) >= 2:
                inline = cells[1]
        parts = re.split(r"[;；]\s*", inline)
        items = [p.strip() for p in parts if p.strip()]
    return items


def state_digest(state: dict[str, Any]) -> str:
    parts = [
        state.get("topic", ""),
        state.get("owner_question", ""),
        format_list(state.get("confirmed_points", [])),
        format_list(state.get("conflicts", [])),
        format_list(state.get("open_questions", [])),
        format_guest_summaries(state.get("guest_summaries", {})),
        format_list(state.get("owner_views", [])),
    ]
    return "\n".join(parts)


def stop_suggestions(state: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    if state.get("stop_recommendation"):
        suggestions.append(state["stop_recommendation"])
    history = state.get("history", [])
    if len(history) >= 2:
        last_two = history[-2:]
        for label, idx in (("confirmed_points", 0), ("conflicts", 1), ("open_questions", 2)):
            if all(history_additions(h)[idx] == 0 for h in last_two):
                suggestions.append(f"连续两轮没有新增 {label}")

    if len(state.get("open_questions", [])) > 5:
        suggestions.append("open_questions 超过 5 个，议题可能发散")

    if len(state_digest(state)) > 1500:
        suggestions.append("meeting_state 摘要超过 1500 字")

    if len(history) >= 2:
        last_guests = [h.get("guest") for h in history[-2:]]
        if last_guests[0] == last_guests[1]:
            suggestions.append("连续两轮同一 Guest 发言，可能重复")

    return suggestions


def owner_pause_message(state: dict[str, Any] | None = None) -> str:
    n = 3
    if state:
        n = state.get("max_round_before_owner", 3)
    return (
        f"\n⏸  Owner 接管 required（已完成 {n} 轮）\n"
        "请选择：\n"
        "  ./council.sh continue        # 继续最多 3 轮\n"
        "  ./council.sh stop            # 停止并生成 final.md\n"
        "  ./council.sh view \"观点\"     # 注入 Owner 观点\n"
        "  ./council.sh ask \"新问题\"    # 更新当前问题\n"
    )


def history_additions(entry: dict[str, Any]) -> tuple[int, int, int]:
    if entry.get("mode") == "parallel":
        return (
            entry.get("confirmed_points_added", 0),
            entry.get("conflicts_added", 0),
            entry.get("open_questions_added", 0),
        )
    return (
        entry.get("confirmed_points_added", entry.get("items_added", 0)),
        entry.get("conflicts_added", 0),
        entry.get("open_questions_added", 0),
    )


def update_stop_recommendation(state: dict[str, Any]) -> None:
    history = state.get("history", [])
    if len(history) < 2:
        state["stop_recommendation"] = ""
        return
    last_two = history[-2:]
    stale = all(
        history_additions(h)[0] == 0 and history_additions(h)[1] == 0 and history_additions(h)[2] == 0
        for h in last_two
    )
    state["stop_recommendation"] = (
        "连续 2 轮无新增 confirmed/conflict/question，建议停止" if stale else ""
    )


def generate_mock_market_context(*, scope: str, topic: str, label: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sections = [
        "当前日期",
        "议题",
        "过去两周市场背景",
        "主要指数表现",
        "美股",
        "A股",
        "港股",
        "黄金",
        "原油",
        "美债",
        "美元",
        "人民币",
        "重要宏观事件",
        "重要政策事件",
        "重要财报事件",
        "需要人工复核的数据点",
        "Source Notes",
    ]
    lines = [f"# Market Context\n", f"[MOCK/{label}]\n"]
    for sec in sections:
        lines.append(f"## {sec}")
        if sec == "当前日期":
            lines.append(today)
        elif sec == "议题":
            lines.append(topic)
        else:
            lines.append(f"数据缺失：{scope} — CLI 不可用，需 Owner 人工补充")
        lines.append("")
    return "\n".join(lines)


def build_research_semantic_obligations(
    state: dict[str, Any], *, prior_claims: list[dict[str, Any]] | None = None
) -> str:
    lines = [
        "5. 你必须至少回应以下三类之一：支持或修正一个 confirmed_point；回应或挑战一个 conflict；回答或细化一个 open_question。"
    ]
    if prior_claims:
        first = prior_claims[0]
        lines.append(
            f"5b. **历史试探性主张（必填）**：对「历史试探性主张」中至少一条写入 claim_responses。"
            f" 优先：{first.get('claim_id', '')} ({first.get('status', 'TENTATIVE')})"
        )
    conflicts = state.get("conflicts", [])
    open_questions = state.get("open_questions", [])
    if conflicts:
        lines.append(
            f"6. **存在分歧（必填）**：优先从「当前分歧」中选择一个 conflict 进行回应或挑战。"
            f" 首个待回应：{conflicts[0]}"
        )
    if open_questions:
        lines.append(
            f"7. **存在未决问题（必填）**：至少尝试关闭一个 open_question，或说明为什么目前无法关闭。"
            f" 首个待处理：{open_questions[0]}"
        )
    return "\n".join(lines)


def build_research_prompt_context(
    state: dict[str, Any], guests: dict[str, Any], guest_name: str, meeting_dir: Path
) -> dict[str, str]:
    question = state.get("next_question") or state.get("current_focus") or state.get("topic", "")
    prior = select_claims_for_injection(state, ROOT)
    prior_text = format_prior_claims_for_prompt(prior)
    inject_errors = validate_injection_text(prior_text)
    if inject_errors:
        raise ValueError("prior_claims 注入校验失败: " + "; ".join(inject_errors))
    return {
        "topic": state.get("topic", ""),
        "next_question": question,
        "market_context": read_market_context(meeting_dir),
        "prior_claims": prior_text,
        "guest_role": guests.get(guest_name, {}).get("role", guest_name),
        "guest_id": guest_name,
        "role_id": guest_role_id(guests, guest_name),
        "confirmed_points": format_list(state.get("confirmed_points", [])),
        "conflicts": format_list(state.get("conflicts", [])),
        "open_questions": format_list(state.get("open_questions", [])),
        "owner_views": format_list(state.get("owner_views", []), empty="(无)"),
        "guest_summaries": format_guest_summaries(state.get("guest_summaries", {})),
        "semantic_obligations": build_research_semantic_obligations(state, prior_claims=prior),
    }


def generate_research_prompt(
    state: dict[str, Any], guests: dict[str, Any], guest_name: str, meeting_dir: Path
) -> str:
    ctx = build_research_prompt_context(state, guests, guest_name, meeting_dir)
    template = GUEST_RESEARCH_TEMPLATE if GUEST_RESEARCH_TEMPLATE.exists() else GUEST_TEMPLATE
    return render_template(template, ctx)


def resolve_selected_guests(state: dict[str, Any], guests: dict[str, Any], roster: list[str]) -> list[str]:
    explicit = state.get("selected_guests") or []
    if explicit:
        return select_guests_for_focus("", roster, guests, explicit=explicit)
    focus = state.get("current_focus") or state.get("next_question") or state.get("topic", "")
    return select_guests_for_focus(focus, roster, guests)


def write_error_file(path: Path, *, guest: str, round_num: int, error: str) -> None:
    body = (
        f"# Guest Error — round {round_tag(round_num)} / {guest}\n\n"
        f"**Time:** {utc_now()}\n\n"
        f"## Error\n\n{error.strip()}\n"
    )
    path.write_text(body, encoding="utf-8")


def process_parallel_guest(
    *,
    meeting_dir: Path,
    state: dict[str, Any],
    guests: dict[str, Any],
    guest_name: str,
    round_num: int,
) -> dict[str, Any]:
    t0 = time.time()
    paths = artifact_paths_research(meeting_dir, round_num, guest_name, round_tag)
    guest_cfg = guests.get(guest_name, {})
    timeout = int(guest_cfg.get("timeout_seconds", 180))

    try:
        for p in paths.values():
            ensure_no_overwrite(p)

        injected_claims = select_claims_for_injection(state, ROOT)
        prompt = generate_research_prompt(state, guests, guest_name, meeting_dir)
        paths["prompt"].write_text(prompt, encoding="utf-8")

        raw_output, raw_mock = invoke_cli(
            guest_cfg.get("command", ""),
            prompt,
            mock_label="guest-cli-missing",
            round_num=round_num,
            guest=guest_name,
            kind="guest",
            timeout_seconds=timeout,
        )
        if raw_mock:
            raw_output = generate_mock_research_output(
                guest=guest_name,
                round_num=round_num,
                label="mock",
                state=state,
                injected_claims=injected_claims,
            )
        paths["raw"].write_text(raw_output.strip() + "\n", encoding="utf-8")

        respond_events = []
        if injected_claims:
            primary_cid = injected_claims[0].get("claim_id", "")
            respond_events = parse_claim_responses_from_raw(
                raw_output,
                claim_id=primary_cid,
                guest=guest_name,
                meeting_id=state["meeting_id"],
                meeting_dir=meeting_dir,
            )
            for ev in respond_events:
                append_event(ROOT, ev)
            if respond_events:
                rebuild_index(ROOT)

        summarizer_cfg = guests.get("summarizer", {})
        sum_timeout = int(summarizer_cfg.get("timeout_seconds", 120))
        summarizer_prompt = SUMMARIZER_TEMPLATE.read_text(encoding="utf-8")
        summarizer_prompt += "\n\n---\n\n## Guest 原始输出\n\n" + raw_output
        summary_body, sum_mock = invoke_cli(
            summarizer_cfg.get("command", ""),
            summarizer_prompt,
            mock_label="summarizer-cli-missing",
            round_num=round_num,
            guest=guest_name,
            kind="summarizer",
            timeout_seconds=sum_timeout,
        )

        parsed = parse_summary_sections(summary_body)
        summary_data = build_summary_json(
            meeting_id=state["meeting_id"],
            round_num=round_num,
            guest=guest_name,
            parsed=parsed,
            raw_text=raw_output,
        )
        paths["summary_json"].write_text(json.dumps(summary_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths["summary_md"].write_text(summary_json_to_md(summary_data), encoding="utf-8")

        duration = round(time.time() - t0, 1)
        return {
            "guest": guest_name,
            "success": True,
            "summary_data": summary_data,
            "duration_s": duration,
            "used_mock_guest": raw_mock,
            "used_mock_summarizer": sum_mock,
            "claim_responds": len(respond_events),
            "prompt_path": str(paths["prompt"].relative_to(meeting_dir)),
            "raw_output_path": str(paths["raw"].relative_to(meeting_dir)),
            "summary_md_path": str(paths["summary_md"].relative_to(meeting_dir)),
            "summary_json_path": str(paths["summary_json"].relative_to(meeting_dir)),
        }
    except Exception as exc:
        duration = round(time.time() - t0, 1)
        err_path = paths.get("error")
        if err_path and not err_path.exists():
            write_error_file(err_path, guest=guest_name, round_num=round_num, error=str(exc))
        return {
            "guest": guest_name,
            "success": False,
            "error": str(exc),
            "duration_s": duration,
            "error_path": str(err_path.relative_to(meeting_dir)) if err_path else "",
        }


def cmd_init(_: argparse.Namespace) -> None:
    dirs = [
        ROOT / "config",
        ROOT / "prompts",
        ROOT / "prompts" / "guest",
        ROOT / "prompts" / "system",
        ROOT / "prompts" / "reports",
        ROOT / "docs",
        ROOT / "docs" / "archive",
        ROOT / "scripts",
        ROOT / "meetings",
        ROOT / "lib",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    ensure_claims_dir(ROOT)

    defaults = {
        CONFIG_FILE: """guests:
  qwen:
    role: "Chief Architect"
    model: "gpu-llama/qwen3.6-35b"
    command: "opencode run -m gpu-llama/qwen3.6-35b --auto"
    enabled: true

  laguna:
    role: "Geopolitical & Policy Risk"
    model: "openrouter/poolside/laguna-m.1:free"
    command: "opencode run -m openrouter/poolside/laguna-m.1:free --auto"
    enabled: true

  north:
    role: "Implementation Planner"
    model: "opencode/north-mini-code-free"
    command: "opencode run -m opencode/north-mini-code-free --auto"
    enabled: true

  mimo:
    role: "Pragmatic Reviewer"
    model: "opencode/mimo-v2.5-free"
    command: "opencode run -m opencode/mimo-v2.5-free --auto"
    enabled: true

  nemo:
    role: "Systems Analyst"
    model: "opencode/nemotron-3-ultra-free"
    command: "opencode run -m opencode/nemotron-3-ultra-free --auto"
    enabled: true

  summarizer:
    role: "Meeting Secretary"
    model: "opencode/deepseek-v4-flash-free"
    command: "opencode run -m opencode/deepseek-v4-flash-free --auto"
    enabled: true
""",
        GUEST_TEMPLATE: """# Council Round Context

你正在参加一个多模型架构会议。

你不是主持人。
你只需要回答当前问题。
不要重复历史。
不要写长报告。
不要提出无关方案。

## 议题

{{topic}}

## Owner 原始问题

{{owner_question}}

## 当前已确认观点

{{confirmed_points}}

## 当前冲突

{{conflicts}}

## 当前未决问题

{{open_questions}}

## Owner 最新观点

{{owner_views}}

## 其他嘉宾观点摘要

{{guest_summaries}}

## 你的角色

{{guest_role}}

## 当前轮问题

{{next_question}}

## 输出格式

判断：
证据：
反方视角：
风险：
建议：
是否需要下一轮：
""",
        SUMMARIZER_TEMPLATE: """你是 Meeting Secretary。

你只负责压缩和结构化。
禁止新增观点。
禁止评价观点。
禁止替 Guest 补充理由。
禁止解决冲突。

请从以下 Guest 原始输出中提取：

1. confirmed_points
2. conflicts
3. open_questions
4. guest_position_summary
5. suggested_next_question

要求：
- 每项尽量短
- 总长度不超过 500 字
- 不允许加入原文没有的判断
- 不允许替 Owner 做决策

请输出稳定 Markdown。
""",
    }

    created = []
    for path, content in defaults.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(str(path.relative_to(ROOT)))

    print("Council Engine initialized.")
    if created:
        print("Created:")
        for item in created:
            print(f"  - {item}")
    else:
        print("All default files already present.")


def cmd_start(args: argparse.Namespace) -> None:
    topic = args.topic.strip()
    if not topic:
        raise SystemExit("Topic cannot be empty.")

    MEETINGS_DIR.mkdir(parents=True, exist_ok=True)
    guests = load_guests()
    roster = guest_roster(guests)
    if not roster:
        raise SystemExit("No enabled guests found in config/guests.yaml")

    meeting_id = datetime.now().strftime("meet-%Y%m%d-%H%M%S")
    meeting_dir = MEETINGS_DIR / meeting_id
    for sub in ("prompts", "raw", "summaries", "errors", "context"):
        (meeting_dir / sub).mkdir(parents=True, exist_ok=False)

    owner_question = args.question.strip() if args.question else topic
    meeting_mode = getattr(args, "mode", "standard") or "standard"
    owner_pause = args.rounds_before_owner
    if owner_pause < 1:
        raise SystemExit("--rounds-before-owner must be >= 1")

    if args.max_rounds is not None:
        max_rounds = args.max_rounds
    elif meeting_mode == "investment":
        max_rounds = 100
    else:
        max_rounds = 12

    output_format = "json"
    round_mode = "serial"
    if meeting_mode == "research":
        output_format = "research"
        round_mode = "parallel"

    state: dict[str, Any] = {
        "meeting_id": meeting_id,
        "topic": topic,
        "owner_question": owner_question,
        "meeting_mode": meeting_mode,
        "round": 0,
        "status": "running",
        "owner_required": False,
        "max_round_before_owner": owner_pause,
        "max_rounds": max_rounds,
        "stale_round_limit": getattr(args, "stale_limit", 5),
        "guest_turns_since_owner": 0,
        "rounds_since_owner": 0,
        "confirmed_points": [],
        "conflicts": [],
        "open_questions": [],
        "guest_summaries": {},
        "owner_views": [],
        "next_speaker": roster[0],
        "next_question": owner_question,
        "history": [],
        "stop_reason": "",
        "output_format": output_format,
        "round_mode": round_mode,
        "selected_guests": [],
        "current_focus": "",
        "stop_recommendation": "",
        "positions": {},
        "challenges": [],
        "verifications": [],
        "round_records": [],
    }
    if meeting_mode == "investment":
        state["round_agenda"] = INVESTMENT_AGENDA
        state["next_question"] = INVESTMENT_AGENDA[0]["question"]
        if INVESTMENT_AGENDA[0]["guest"] in roster:
            state["next_speaker"] = INVESTMENT_AGENDA[0]["guest"]

    save_state(meeting_dir, state)
    CURRENT_MEETING_FILE.write_text(meeting_id + "\n", encoding="utf-8")

    print(f"Meeting started: {meeting_id}")
    print(f"Topic: {topic}")
    print(f"Mode: {meeting_mode}")
    if meeting_mode == "investment":
        print(f"Max rounds: {state['max_rounds']} | Stale limit: {state['stale_round_limit']}")
        print("Roles: qwen=宏观 | laguna=地缘政策 | north=大宗 | mimo=股票 | nemo=利率外汇")
    elif meeting_mode == "research":
        print(f"Mode: research (parallel) | Max rounds: {state['max_rounds']}")
        print(f"Rounds before owner pause: {owner_pause}")
        print("Next: ./council.sh context \"范围\" && ./council.sh select ... && ./council.sh run-parallel")
    else:
        print(f"Rounds before owner pause: {owner_pause} | Max rounds: {state['max_rounds']}")
    print(f"Directory: {meeting_dir}")
    print(f"First speaker: {state['next_speaker']}")
    if meeting_mode == "investment":
        print("Next: ./council.sh run-auto")
    elif meeting_mode == "research":
        pass
    else:
        print("Next: ./council.sh run  (or run-parallel for research runtime)")


def generate_round_prompt(state: dict[str, Any], guests: dict[str, Any], guest_name: str, round_num: int) -> str:
    if is_investment_mode(state):
        state = dict(state)
        state["next_question"] = resolve_round_question(state, round_num, guest_name)
    ctx = build_prompt_context(state, guests, guest_name, round_num)
    return render_template(guest_template_path(state), ctx)


def cmd_next(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    guests = load_guests()
    roster = guest_roster(guests)
    guest_name = next_guest_name(state, roster)
    if not guest_name:
        raise SystemExit("No guest available.")

    preview_round = state["round"] + 1
    prompt = generate_round_prompt(state, guests, guest_name, preview_round)

    print(f"--- Next prompt preview (round {round_tag(preview_round)}, guest: {guest_name}) ---")
    print(prompt)
    print("--- end preview (not saved, models not invoked) ---")


def run_one_round(meeting_dir: Path, *, quiet: bool = False) -> str | None:
    """Run one guest turn. Returns auto-stop reason if meeting should end."""
    state = load_state(meeting_dir)
    guests = load_guests()
    roster = guest_roster(guests)

    if state.get("status") == "stopped":
        raise SystemExit("Meeting already stopped. Use ./council.sh start to begin a new one.")

    if state.get("owner_required") and not is_investment_mode(state):
        print(owner_pause_message(state))
        raise SystemExit(2)

    pre_stop = check_investment_auto_stop(state)
    if pre_stop:
        return pre_stop

    if is_investment_mode(state) and state["round"] >= state.get("max_rounds", 100):
        return f"已达最大轮次 {state.get('max_rounds', 100)}"

    guest_name = next_guest_name(state, roster)
    if not guest_name:
        raise SystemExit("No guest available.")

    guest_cfg = guests.get(guest_name, {})
    guest_cmd = guest_cfg.get("command", "")
    role_id = guest_role_id(guests, guest_name)
    json_mode = is_json_mode(state)

    round_num = state["round"] + 1
    paths = artifact_paths(meeting_dir, round_num, guest_name, json_mode=json_mode)
    for p in paths.values():
        ensure_no_overwrite(p)

    if is_investment_mode(state):
        state["next_question"] = resolve_round_question(state, round_num, guest_name)

    focus = state.get("next_question", "")
    prompt = generate_round_prompt(state, guests, guest_name, round_num)
    paths["prompt"].write_text(prompt, encoding="utf-8")

    if not quiet:
        print(f"Round {round_tag(round_num)} — guest: {guest_name} ({role_id})")
        print(f"Focus: {focus[:100]}...")
        print(f"Prompt saved: {paths['prompt']}")

    if json_mode:
        raw_output, raw_mock = invoke_cli(
            guest_cmd,
            prompt,
            mock_label="guest-cli-missing",
            round_num=round_num,
            guest=guest_name,
            kind="guest",
        )
        if raw_mock:
            raw_output = generate_mock_guest_json(
                guest=guest_name,
                role_id=role_id,
                round_num=round_num,
                focus=focus,
                label="mock",
            )

        validation_errors: list[str] = []
        try:
            guest_data = extract_json_from_text(raw_output)
            validation_errors = validate_guest_json(
                guest_data, guest_name=guest_name, role_id=role_id, round_num=round_num
            )
            if validation_errors:
                raise ValueError("; ".join(validation_errors))
        except (json.JSONDecodeError, ValueError) as exc:
            validation_errors = validation_errors or [str(exc)]
            guest_data = json.loads(
                generate_mock_guest_json(
                    guest=guest_name,
                    role_id=role_id,
                    round_num=round_num,
                    focus=focus,
                    label=f"invalid-json: {validation_errors[0][:80]}",
                )
            )
            raw_mock = True

        paths["raw"].write_text(json.dumps(guest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not quiet:
            print(f"JSON saved: {paths['raw']}" + (" [MOCK/FIXED]" if raw_mock else ""))
            if validation_errors and not raw_mock:
                print(f"  validation warnings: {validation_errors}")

        counts = merge_guest_json_into_state(state, guest_data)
        history_entry: dict[str, Any] = {
            "round": round_num,
            "guest": guest_name,
            "role": role_id,
            "prompt_path": str(paths["prompt"].relative_to(meeting_dir)),
            "json_path": str(paths["raw"].relative_to(meeting_dir)),
            "timestamp": utc_now(),
            "items_added": counts["items_added"],
            "confidence": guest_data.get("confidence"),
            "position": guest_data.get("position"),
            "used_mock_guest": raw_mock,
            "validation_errors": validation_errors,
        }
    else:
        summarizer_cfg = guests.get("summarizer", {})
        summarizer_cmd = summarizer_cfg.get("command", "")
        raw_output, raw_mock = invoke_cli(
            guest_cmd,
            prompt,
            mock_label="guest-cli-missing",
            round_num=round_num,
            guest=guest_name,
            kind="guest",
        )
        paths["raw"].write_text(raw_output.strip() + "\n", encoding="utf-8")
        if not quiet:
            print(f"Raw saved: {paths['raw']}" + (" [MOCK]" if raw_mock else ""))

        summarizer_prompt = SUMMARIZER_TEMPLATE.read_text(encoding="utf-8")
        summarizer_prompt += "\n\n---\n\n## Guest 原始输出\n\n" + raw_output
        summary_body, sum_mock = invoke_cli(
            summarizer_cmd,
            summarizer_prompt,
            mock_label="summarizer-cli-missing",
            round_num=round_num,
            guest=guest_name,
            kind="summarizer",
        )
        write_summary_file(
            paths["summary"],
            meeting_id=state["meeting_id"],
            round_num=round_num,
            guest=guest_name,
            body=summary_body,
        )
        if not quiet:
            print(f"Summary saved: {paths['summary']}" + (" [MOCK]" if sum_mock else ""))

        parsed = parse_summary_sections(summary_body)
        counts = apply_parsed_summary(state, guest_name, parsed)
        if parsed["suggested_next_question"] and not is_investment_mode(state):
            state["next_question"] = parsed["suggested_next_question"]

        history_entry = {
            "round": round_num,
            "guest": guest_name,
            "prompt_path": str(paths["prompt"].relative_to(meeting_dir)),
            "raw_output_path": str(paths["raw"].relative_to(meeting_dir)),
            "summary_path": str(paths["summary"].relative_to(meeting_dir)),
            "timestamp": utc_now(),
            "confirmed_points_added": counts["confirmed_points_added"],
            "conflicts_added": counts["conflicts_added"],
            "open_questions_added": counts["open_questions_added"],
            "used_mock_guest": raw_mock,
            "used_mock_summarizer": sum_mock,
        }

    state["round"] = round_num
    state["guest_turns_since_owner"] = state.get("guest_turns_since_owner", 0) + 1
    state["rounds_since_owner"] = state.get("rounds_since_owner", 0) + 1
    state["history"].append(history_entry)

    state["next_speaker"] = rotate_guest(guest_name, roster)
    if is_investment_mode(state):
        state["next_question"] = resolve_round_question(state, round_num + 1, state["next_speaker"])
    elif not json_mode and parsed.get("suggested_next_question"):
        state["next_question"] = parsed["suggested_next_question"]

    if not is_investment_mode(state) and state["rounds_since_owner"] >= state.get("max_round_before_owner", 3):
        state["owner_required"] = True

    update_stop_recommendation(state)
    save_state(meeting_dir, state)

    if not quiet:
        suggestions = stop_suggestions(state)
        if suggestions:
            print("\n💡 建议停止条件（非强制，Owner 决定）：")
            for s in suggestions:
                print(f"  - {s}")

        if state["owner_required"]:
            print(owner_pause_message(state))
        else:
            print(f"\nNext speaker: {state['next_speaker']}")
            print("Run again: ./council.sh run")

    return check_investment_auto_stop(state)


def run_one_parallel_round(meeting_dir: Path, *, quiet: bool = False) -> str | None:
    """Run one parallel round with selected_guests. Returns stop reason if needed."""
    state = load_state(meeting_dir)
    guests = load_guests()
    roster = guest_roster(guests)
    full_cfg = load_full_config(CONFIG_FILE)
    max_workers = max_parallel_from_config(full_cfg)

    if state.get("status") == "stopped":
        raise SystemExit("Meeting already stopped.")

    if state.get("owner_required"):
        print(owner_pause_message(state))
        raise SystemExit(2)

    if state["round"] >= state.get("max_rounds", 12):
        return f"已达最大轮次 {state.get('max_rounds', 12)}"

    round_num = state["round"] + 1
    selected = resolve_selected_guests(state, guests, roster)
    if not selected:
        raise SystemExit("No guests selected for parallel round.")

    parallel_batch = [g for g in selected if guests.get(g, {}).get("allow_parallel", True)]
    serial_batch = [g for g in selected if not guests.get(g, {}).get("allow_parallel", True)]

    if not quiet:
        print(f"Round {round_tag(round_num)} — parallel guests: {', '.join(selected)}")
        print(f"max_parallel={max_workers} | parallel={len(parallel_batch)} serial={len(serial_batch)}")

    t_round = time.time()
    entries: list[dict[str, Any]] = []

    def run_guest(guest_name: str) -> dict[str, Any]:
        return process_parallel_guest(
            meeting_dir=meeting_dir,
            state=state,
            guests=guests,
            guest_name=guest_name,
            round_num=round_num,
        )

    if parallel_batch:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(parallel_batch))) as pool:
            futures = {pool.submit(run_guest, g): g for g in parallel_batch}
            for fut in as_completed(futures):
                entries.append(fut.result())
    for guest_name in serial_batch:
        entries.append(run_guest(guest_name))

    entries.sort(key=lambda e: selected.index(e["guest"]) if e["guest"] in selected else 999)

    cp_total = cf_total = oq_total = 0
    for entry in entries:
        if not entry.get("success"):
            if not quiet:
                print(f"  ✗ {entry['guest']}: {entry.get('error', 'failed')[:120]}")
            continue
        try:
            counts = apply_summary_json_to_state(state, entry["summary_data"])
            entry["confirmed_points_added"] = counts["confirmed_points_added"]
            entry["conflicts_added"] = counts["conflicts_added"]
            entry["open_questions_added"] = counts["open_questions_added"]
            cp_total += counts["confirmed_points_added"]
            cf_total += counts["conflicts_added"]
            oq_total += counts["open_questions_added"]
            if not quiet:
                print(
                    f"  ✓ {entry['guest']} (+cp:{counts['confirmed_points_added']} "
                    f"+cf:{counts['conflicts_added']} +oq:{counts['open_questions_added']}) "
                    f"{entry.get('duration_s', '?')}s"
                )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            entry["success"] = False
            entry["parse_error"] = str(exc)
            err_paths = artifact_paths_research(meeting_dir, round_num, entry["guest"], round_tag)
            if not err_paths["error"].exists():
                write_error_file(
                    err_paths["error"],
                    guest=entry["guest"],
                    round_num=round_num,
                    error=f"summary.json apply failed: {exc}",
                )
            if not quiet:
                print(f"  ✗ {entry['guest']}: summary.json parse failed — state not updated")

    round_duration = round(time.time() - t_round, 1)
    state["round"] = round_num
    state["round_mode"] = "parallel"
    state["rounds_since_owner"] = state.get("rounds_since_owner", 0) + 1
    state["guest_turns_since_owner"] = state.get("guest_turns_since_owner", 0) + sum(
        1 for e in entries if e.get("success")
    )
    state["selected_guests"] = []
    state["history"].append(
        {
            "mode": "parallel",
            "round": round_num,
            "guests": selected,
            "entries": entries,
            "timestamp": utc_now(),
            "duration_s": round_duration,
            "confirmed_points_added": cp_total,
            "conflicts_added": cf_total,
            "open_questions_added": oq_total,
        }
    )

    if state["rounds_since_owner"] >= state.get("max_round_before_owner", 3):
        state["owner_required"] = True

    update_stop_recommendation(state)
    save_state(meeting_dir, state)

    if round_num >= 2:
        ok, loop_errors = verify_research_semantic_loop(meeting_dir, round_num=round_num)
        if not ok:
            print("\n⚠️  Research 语义闭环验收失败：")
            for err in loop_errors:
                print(f"  - {err}")
        elif not quiet:
            print(f"\n✓ Research 语义闭环验收通过（round {round_tag(round_num)}）")

    if not quiet:
        print(f"\nRound {round_tag(round_num)} done in {round_duration}s")
        suggestions = stop_suggestions(state)
        if suggestions:
            print("\n💡 建议停止条件（非强制，Owner 决定）：")
            for s in suggestions:
                print(f"  - {s}")
        if state["owner_required"]:
            print(owner_pause_message(state))
        else:
            print("Run again: ./council.sh run-parallel")

    if state["round"] >= state.get("max_rounds", 12):
        return f"已达最大轮次 {state.get('max_rounds', 12)}"
    return None


def cmd_run_parallel(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    reason = run_one_parallel_round(meeting_dir)
    if reason:
        print(f"\n🛑 自动终止条件触发: {reason}")
        finish_meeting(meeting_dir, reason)


def cmd_select(args: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    guests = load_guests()
    roster = guest_roster(guests)

    names = [a for a in args.guests if a.strip()]
    if not names:
        raise SystemExit("Usage: ./council.sh select <guest> [guest...]")

    selected: list[str] = []
    for name in names:
        resolved = resolve_guest_alias(name, roster)
        if not resolved:
            raise SystemExit(f"Unknown or disabled guest: {name}")
        if resolved not in selected:
            selected.append(resolved)

    state["selected_guests"] = selected
    save_state(meeting_dir, state)
    print(f"Next parallel round guests: {', '.join(selected)}")
    print("Run: ./council.sh run-parallel")


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

    collector = guests.get("reporter", guests.get("qwen", {}))
    cmd = collector.get("command", "")
    timeout = int(collector.get("timeout_seconds", 300))
    body, used_mock = invoke_cli(
        cmd,
        prompt,
        mock_label="context-collector",
        round_num=state.get("round", 0),
        guest="context",
        kind="guest",
        timeout_seconds=timeout,
    )
    if used_mock or not body.strip():
        body = generate_mock_market_context(scope=scope, topic=state.get("topic", ""), label="mock")

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
    if used_mock:
        print("[MOCK] Context generated offline — verify data before decisions.")


def cmd_report(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    metrics = compute_metrics(meeting_dir, state)
    inv_path = meeting_dir / "investment_report.md"
    exp_path = meeting_dir / "council_experiment_report.md"
    inv_path.write_text(generate_council_investment_report(state, meeting_dir, metrics), encoding="utf-8")
    exp_path.write_text(generate_council_experiment_report(state, metrics), encoding="utf-8")
    print(f"Investment report: {inv_path}")
    print(f"Experiment report: {exp_path}")


def cmd_metrics(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    metrics = compute_metrics(meeting_dir, state)

    md_path = meeting_dir / "metrics.md"
    json_path = meeting_dir / "metrics.json"
    md_path.write_text(metrics_markdown(metrics), encoding="utf-8")
    json_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(metrics_markdown(metrics))
    print(f"Saved: {md_path}")
    print(f"Saved: {json_path}")


def cmd_run(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    reason = run_one_round(meeting_dir)
    if reason:
        print(f"\n🛑 自动终止条件触发: {reason}")
        finish_meeting(meeting_dir, reason)


def cmd_summary(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)

    print(f"# Meeting Summary — {state['meeting_id']}\n")
    print(f"**Topic:** {state['topic']}")
    print(f"**Status:** {state['status']}")
    print(f"**Round:** {state['round']}")
    print(f"**Owner required:** {state.get('owner_required', False)}\n")

    if is_json_mode(state):
        print("## Positions")
        print(json.dumps(state.get("positions", {}), ensure_ascii=False, indent=2))
        print("\n## Challenges")
        print(json.dumps(state.get("challenges", []), ensure_ascii=False, indent=2))
        print("\n## Verifications")
        print(format_list(state.get("verifications", [])))
    else:
        print("## Confirmed Points")
        print(format_list(state.get("confirmed_points", [])))
        print("\n## Conflicts")
        print(format_list(state.get("conflicts", [])))
        print("\n## Open Questions")
        print(format_list(state.get("open_questions", [])))
        print("\n## Guest Summaries")
        print(format_guest_summaries(state.get("guest_summaries", {})))
    print("\n## Owner Views")
    print(format_list(state.get("owner_views", []), empty="(无)"))
    print(f"\n## Current Question\n{state.get('next_question', '')}")

    suggestions = stop_suggestions(state)
    if suggestions:
        print("\n## Stop Suggestions")
        for s in suggestions:
            print(f"- {s}")


def cmd_status(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    print(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_continue(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    if state.get("status") == "stopped":
        raise SystemExit("Meeting already stopped.")
    state["owner_required"] = False
    state["guest_turns_since_owner"] = 0
    state["rounds_since_owner"] = 0
    state["status"] = "running"
    save_state(meeting_dir, state)
    pause = state.get("max_round_before_owner", 3)
    print(f"Owner control released. Up to {pause} more rounds allowed.")
    print(f"Next speaker: {state.get('next_speaker', '')}")
    print("Run: ./council.sh run")


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

    metrics = compute_metrics(meeting_dir, state)
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


def cmd_stop(_: argparse.Namespace) -> None:
    finish_meeting(get_current_meeting_dir(), "manual stop by owner")


def cmd_run_auto(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    if not is_investment_mode(state):
        raise SystemExit("run-auto 仅适用于 investment 模式。请使用: ./council.sh start \"议题\" --mode investment")

    print(f"Starting auto-run: {state['meeting_id']}")
    print(f"Max rounds: {state.get('max_rounds', 100)} | Stale limit: {state.get('stale_round_limit', 5)}")

    while state.get("status") == "running":
        reason = run_one_round(meeting_dir, quiet=True)
        state = load_state(meeting_dir)
        last = state["history"][-1]
        if is_json_mode(state):
            print(
                f"  ✓ Round {state['round']:03d} / {last['guest']} "
                f"conf={last.get('confidence', '?')} items+={last.get('items_added', 0)} "
                f"pos={str(last.get('position', ''))[:40]}"
            )
        else:
            print(
                f"  ✓ Round {state['round']:03d} / {last['guest']} "
                f"(+cp:{last.get('confirmed_points_added', 0)} "
                f"+cf:{last.get('conflicts_added', 0)} "
                f"+oq:{last.get('open_questions_added', 0)})"
            )
        if reason:
            print(f"\n🛑 Auto-stop: {reason}")
            finish_meeting(meeting_dir, reason)
            return
        if state["round"] >= state.get("max_rounds", 100):
            finish_meeting(meeting_dir, f"已达最大轮次 {state.get('max_rounds', 100)}")
            return

    print("Meeting already stopped.")


def cmd_view(args: argparse.Namespace) -> None:
    view = args.text.strip()
    if not view:
        raise SystemExit("View text cannot be empty.")
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    state["owner_views"].append(view)
    save_state(meeting_dir, state)
    print(f"Owner view recorded ({len(state['owner_views'])} total).")


def cmd_ask(args: argparse.Namespace) -> None:
    question = args.text.strip()
    if not question:
        raise SystemExit("Question cannot be empty.")
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    state["next_question"] = question
    save_state(meeting_dir, state)
    print(f"Next question updated: {question}")


def cmd_repair_state(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)

    renamed = migrate_guest_names(meeting_dir, state)
    rebuild_state_from_summaries(state, meeting_dir)
    save_state(meeting_dir, state)

    print(f"Repaired meeting: {state['meeting_id']}")
    if renamed:
        print("\nRenamed artifacts:")
        for item in renamed:
            print(f"  - {item}")
    print("\nState rebuilt from summaries:")
    print(f"  confirmed_points: {len(state['confirmed_points'])}")
    print(f"  conflicts: {len(state['conflicts'])}")
    print(f"  open_questions: {len(state['open_questions'])}")
    print(f"  guest_summaries: {', '.join(state['guest_summaries'].keys()) or '(none)'}")


def cmd_audit_summary(args: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    round_num = int(args.round)
    guest = LEGACY_GUEST_MAP.get(args.guest, args.guest)

    research_paths = artifact_paths_research(meeting_dir, round_num, guest, round_tag)
    json_paths = artifact_paths(meeting_dir, round_num, guest, json_mode=True)
    md_paths = artifact_paths(meeting_dir, round_num, guest, json_mode=False)

    use_research = research_paths["raw"].exists() or is_research_mode(state)
    if use_research:
        paths = research_paths
        audit_items = [
            ("Prompt", paths["prompt"]),
            ("Raw", paths["raw"]),
            ("Summary MD", paths["summary_md"]),
            ("Summary JSON", paths["summary_json"]),
            ("Error", paths["error"]),
        ]
    elif is_json_mode(state):
        paths = json_paths
        audit_items = [("Prompt", paths["prompt"]), ("JSON Raw", paths["raw"])]
    else:
        paths = md_paths
        audit_items = [("Prompt", paths["prompt"]), ("Raw", paths["raw"])]
        if "summary" in paths:
            audit_items.append(("Summary MD", paths["summary"]))

    print(f"Audit — round {round_tag(round_num)}, guest: {guest}\n")
    for label, path in audit_items:
        exists = path.exists()
        print(f"{label}: {path} {'✓' if exists else '✗ MISSING'}")
        if exists and label != "Prompt":
            content = path.read_text(encoding="utf-8")
            print("--- preview ---")
            print(content[:800])
            if len(content) > 800:
                print("... (truncated)")


def parse_from_state_ref(ref: str) -> tuple[str, int]:
    m = re.match(r"^(confirmed_points|conflicts|open_questions)\[(\d+)\]$", ref.strip())
    if not m:
        raise SystemExit(f"Invalid --from-state: {ref} (expected e.g. conflicts[0])")
    return m.group(1), int(m.group(2))


def resolve_meeting_dir(meeting_id: str | None) -> Path:
    if meeting_id:
        meeting_dir = MEETINGS_DIR / meeting_id.strip()
        if not meeting_dir.exists():
            raise SystemExit(f"Meeting not found: {meeting_dir}")
        return meeting_dir
    return get_current_meeting_dir()


def build_scope_from_args(args: argparse.Namespace) -> dict[str, Any]:
    subjects = [s.strip() for s in (args.subjects or "").split(",") if s.strip()]
    regime_tags = [s.strip() for s in (args.regime_tags or "").split(",") if s.strip()]
    conditions = [s.strip() for s in (args.conditions or "").split(";") if s.strip()]
    return {
        "domain": (args.domain or "").strip(),
        "subjects": subjects,
        "regime_tags": regime_tags,
        "valid_from": (args.valid_from or "").strip(),
        "valid_until": (args.valid_until or "").strip(),
        "conditions": conditions,
        "exclusions": [],
    }


def cmd_claim_promote(args: argparse.Namespace) -> None:
    field, index = parse_from_state_ref(args.from_state)
    meeting_dir = resolve_meeting_dir(args.meeting)
    state = load_state(meeting_dir)
    scope = build_scope_from_args(args)

    scope_errors = validate_scope(scope)
    if scope_errors:
        raise SystemExit("scope 校验失败:\n  - " + "\n  - ".join(scope_errors))

    items = state.get(field, [])
    if index >= len(items):
        raise SystemExit(f"{field}[{index}] 不存在（共 {len(items)} 条）")
    statement = str(items[index]).strip()

    evidence_refs = [e.strip() for e in (args.evidence or []) if e.strip()]
    promo_errors = validate_promotion_candidate(
        statement=statement,
        evidence_refs=evidence_refs,
        meeting_dir=meeting_dir,
        state=state,
        field=field,
        index=index,
    )
    if promo_errors and not args.owner_override:
        raise SystemExit("晋升拒绝:\n  - " + "\n  - ".join(promo_errors))

    claim_id = next_claim_id(ROOT)
    fingerprint = compute_fingerprint(statement, scope)
    event: dict[str, Any] = {
        "event": "PROMOTE",
        "claim_id": claim_id,
        "fingerprint": fingerprint,
        "statement": statement,
        "scope": scope,
        "epistemic_status": "TENTATIVE",
        "evidence_refs": evidence_refs,
        "derived_from_meeting": meeting_dir.name,
        "derived_from_state_ref": f"{field}[{index}]",
        "promoted_by": "owner_override" if args.owner_override else "owner",
        "ts": utc_now(),
    }
    if args.owner_override and promo_errors:
        event["override_note"] = "; ".join(promo_errors)

    append_event(ROOT, event)
    index_data = rebuild_index(ROOT)
    print(f"Promoted {claim_id} → TENTATIVE")
    print(f"Statement: {statement[:120]}{'...' if len(statement) > 120 else ''}")
    print(f"Ledger: {ROOT / 'claims' / 'claims.jsonl'}")
    print(f"Index claims: {index_data.get('claim_count', 0)}")


def cmd_claim_retire(args: argparse.Namespace) -> None:
    claim_id = args.claim_id.strip()
    if not re.match(r"^clm-\d+$", claim_id):
        raise SystemExit(f"Invalid claim_id: {claim_id}")

    index = load_index(ROOT)
    if claim_id not in index.get("claims", {}):
        raise SystemExit(f"Unknown claim: {claim_id}")

    event = {
        "event": "RETIRE",
        "claim_id": claim_id,
        "reason": (args.reason or "owner decision").strip(),
        "actor": "owner",
        "ts": utc_now(),
    }
    append_event(ROOT, event)
    index_data = rebuild_index(ROOT)
    view = index_data.get("claims", {}).get(claim_id, {})
    print(f"Retired {claim_id} → {view.get('status', 'RETIRED')}")
    print(f"Reason: {event['reason']}")


def cmd_claim_rebuild_index(_: argparse.Namespace) -> None:
    index_data = rebuild_index(ROOT)
    print(f"Rebuilt claims_index.json — {index_data.get('claim_count', 0)} claims")
    print(f"Path: {ROOT / 'claims' / 'claims_index.json'}")


def cmd_claim_list(_: argparse.Namespace) -> None:
    index = load_index(ROOT)
    claims = index.get("claims", {})
    if not claims:
        print("(无主张)")
        return
    for cid in sorted(claims.keys()):
        view = claims[cid]
        stmt = view.get("statement", "")
        short = stmt[:80] + ("..." if len(stmt) > 80 else "")
        print(f"{cid} [{view.get('status', '?')}] {short}")


def cmd_claim_verify(_: argparse.Namespace) -> None:
    ok, errors = verify_three_meeting_chain(ROOT)
    if ok:
        print("✓ Claim Lifecycle V0.2 验收通过")
        index = load_index(ROOT)
        for cid, view in sorted(index.get("claims", {}).items()):
            print(f"  {cid}: {view.get('status')} (support={view.get('support_count', 0)})")
        return
    print("✗ Claim Lifecycle 验收失败:")
    for err in errors:
        print(f"  - {err}")
    raise SystemExit(1)


def cmd_claim(args: argparse.Namespace) -> None:
    handlers = {
        "promote": cmd_claim_promote,
        "retire": cmd_claim_retire,
        "rebuild-index": cmd_claim_rebuild_index,
        "list": cmd_claim_list,
        "verify": cmd_claim_verify,
    }
    handler = handlers.get(args.claim_cmd)
    if not handler:
        raise SystemExit(f"Unknown claim subcommand: {args.claim_cmd}")
    handler(args)


def cmd_tui(_: argparse.Namespace) -> None:
    if not shutil.which("tmux"):
        raise SystemExit("tmux not found. Install tmux or use CLI commands directly.")

    meeting_dir = get_current_meeting_dir()
    session = f"council-{meeting_dir.name}"

    if subprocess.run(["tmux", "has-session", "-t", session], capture_output=True).returncode == 0:
        subprocess.run(["tmux", "attach", "-t", session])
        return

    state_file = meeting_dir / "meeting_state.json"
    log_file = meeting_dir / "owner_console.log"
    log_file.touch(exist_ok=True)

    latest_raw = "(no raw output yet)"
    history = load_state(meeting_dir).get("history", [])
    if history:
        latest_raw = str(meeting_dir / history[-1]["raw_output_path"])

    council_sh = ROOT / "council.sh"
    cmds = [
        f"tmux new-session -d -s {session} -n council",
        f"tmux send-keys -t {session} 'watch -n2 cat {state_file}' C-m",
        f"tmux split-window -h -t {session}",
        f"tmux send-keys -t {session} 'watch -n2 cat {latest_raw}' C-m",
        f"tmux split-window -v -t {session}",
        (
            f"tmux send-keys -t {session} 'echo Council Owner Console && "
            f"echo Commands: continue | stop | view | ask | run && tail -f {log_file}' C-m"
        ),
        f"tmux select-pane -t {session}:0.0",
        f"tmux attach -t {session}",
    ]
    for c in cmds[:-1]:
        subprocess.run(c, shell=True, check=True)
    os.execvp("tmux", ["tmux", "attach", "-t", session])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="council",
        description="Council Engine V0.1 — deterministic multi-model meeting workflow",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize directories, config, and templates")

    p_start = sub.add_parser("start", help="Start a new meeting")
    p_start.add_argument("topic", help="Meeting topic")
    p_start.add_argument("-q", "--question", help="Owner original question (defaults to topic)")
    p_start.add_argument(
        "-r",
        "--rounds-before-owner",
        type=int,
        default=3,
        help="Guest turns before owner pause (default: 3)",
    )
    p_start.add_argument(
        "--mode",
        choices=["standard", "investment", "research"],
        default="standard",
        help="Meeting mode: standard, investment, or research (parallel)",
    )
    p_start.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Max rounds (default: 12 standard/research, 100 investment)",
    )
    p_start.add_argument(
        "--stale-limit",
        type=int,
        default=5,
        help="Auto-stop after N stale rounds in investment mode (default: 5)",
    )

    sub.add_parser("run", help="Run next guest turn (prompt → guest → summarizer)")
    sub.add_parser("run-parallel", help="Run parallel round with selected_guests")
    sub.add_parser("run-auto", help="Auto-run investment committee until stop condition")
    sub.add_parser("metrics", help="Compute and save meeting metrics")
    sub.add_parser("report", help="Generate investment_report.md + council_experiment_report.md")

    p_select = sub.add_parser("select", help="Set guests for next parallel round")
    p_select.add_argument("guests", nargs="+", help="Guest ids or aliases (claude, grok, ...)")

    p_context = sub.add_parser("context", help="Generate shared market_context")
    p_context.add_argument("scope", help="Market scope / focus for context collection")
    sub.add_parser("next", help="Preview next prompt without invoking models")
    sub.add_parser("summary", help="Show meeting summary")
    sub.add_parser("status", help="Show meeting_state.json")
    sub.add_parser("continue", help="Release owner_required, allow 3 more turns")
    sub.add_parser("stop", help="Stop meeting and write final.md")

    p_view = sub.add_parser("view", help="Record an owner view")
    p_view.add_argument("text", help="Owner viewpoint text")

    p_ask = sub.add_parser("ask", help="Update next question")
    p_ask.add_argument("text", help="New question")

    p_audit = sub.add_parser("audit-summary", help="Audit prompt/raw/summary for a round")
    p_audit.add_argument("round", help="Round number (e.g. 1 or 001)")
    p_audit.add_argument("guest", help="Guest name (e.g. qwen)")

    sub.add_parser("repair-state", help="Migrate legacy guest names and rebuild state from summaries")
    sub.add_parser("tui", help="Optional tmux-based TUI")

    p_claim = sub.add_parser("claim", help="Claim Lifecycle V0.2 — ledger + index")
    claim_sub = p_claim.add_subparsers(dest="claim_cmd", required=True)

    p_promote = claim_sub.add_parser("promote", help="Owner promote state item to TENTATIVE claim")
    p_promote.add_argument(
        "--from-state",
        required=True,
        help="State ref e.g. conflicts[0] or confirmed_points[2]",
    )
    p_promote.add_argument("--meeting", help="Source meeting id (default: current)")
    p_promote.add_argument("--domain", required=True, help="scope.domain e.g. finance")
    p_promote.add_argument("--subjects", required=True, help="Comma-separated scope.subjects")
    p_promote.add_argument("--regime-tags", default="", help="Comma-separated regime_tags")
    p_promote.add_argument("--valid-from", default="", help="scope.valid_from YYYY-MM-DD")
    p_promote.add_argument("--valid-until", default="", help="scope.valid_until YYYY-MM-DD")
    p_promote.add_argument("--conditions", default="", help="Semicolon-separated scope.conditions")
    p_promote.add_argument(
        "--evidence",
        action="append",
        required=True,
        help="Evidence path relative to meeting (repeatable)",
    )
    p_promote.add_argument(
        "--owner-override",
        action="store_true",
        help="Bypass non-promotion validator with audit note",
    )

    p_retire = claim_sub.add_parser("retire", help="Owner retire a claim")
    p_retire.add_argument("claim_id", help="e.g. clm-000001")
    p_retire.add_argument("--reason", default="owner decision")

    claim_sub.add_parser("rebuild-index", help="Rebuild claims_index.json from ledger")
    claim_sub.add_parser("list", help="List claims from index")
    claim_sub.add_parser("verify", help="Verify three-meeting claim lifecycle chain")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "init": cmd_init,
        "start": cmd_start,
        "run": cmd_run,
        "run-parallel": cmd_run_parallel,
        "run-auto": cmd_run_auto,
        "next": cmd_next,
        "summary": cmd_summary,
        "status": cmd_status,
        "continue": cmd_continue,
        "stop": cmd_stop,
        "view": cmd_view,
        "ask": cmd_ask,
        "select": cmd_select,
        "context": cmd_context,
        "metrics": cmd_metrics,
        "report": cmd_report,
        "audit-summary": cmd_audit_summary,
        "repair-state": cmd_repair_state,
        "tui": cmd_tui,
        "claim": cmd_claim,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()