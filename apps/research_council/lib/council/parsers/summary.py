"""Summary text parsing, merge helpers, and summarizer runner."""
from __future__ import annotations

import re
from typing import Any

from council.config import SECTION_ALIASES, SECTION_KEYS, SUMMARIZER_TEMPLATE
from council.cli_runner import invoke_cli
from council.formatting import round_tag
from council.parsers.mock_filter import is_mock_semantic_item


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


def filter_semantic_items(items: list[str]) -> list[str]:
    return [item for item in items if item and not is_mock_semantic_item(item)]


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$", text)
    if fence:
        return fence.group(1).strip()
    return text


def truncate_for_summarizer(raw: str, *, max_chars: int = 6000) -> str:
    raw = raw.strip()
    if len(raw) <= max_chars:
        return raw
    head = max_chars * 2 // 3
    tail = max_chars - head - 40
    return raw[:head] + "\n\n...[truncated for summarizer]...\n\n" + raw[-tail:]


def fallback_summary_from_research_raw(raw: str, *, guest: str, round_num: int) -> str:
    """Heuristic summary when summarizer CLI times out — avoids MOCK pollution."""
    sections: dict[str, list[str]] = {
        "confirmed_points": [],
        "conflicts": [],
        "open_questions": [],
    }
    current: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if re.match(r"^已确认事实[：:]?\s*$", stripped):
            current = "confirmed_points"
            continue
        if re.match(r"^(合理推断|不确定事项|风险)[：:]?\s*$", stripped):
            current = "open_questions"
            continue
        if re.match(r"^反方视角[：:]?\s*$", stripped):
            current = "conflicts"
            continue
        if re.match(r"^(证据|建议|claim_responses|是否需要下一轮)[：:]?\s*$", stripped):
            current = None
            continue
        if current and stripped.startswith(("-", "•", "*")):
            item = stripped.lstrip("-•* ").strip()
            if item and len(item) > 4:
                sections[current].append(item[:240])
        elif current and stripped and not stripped.startswith("#"):
            sections[current].append(stripped[:240])

    judgment = ""
    m = re.search(r"判断[：:]\s*\n(.+?)(?=\n\n|\n已确认事实)", raw, re.S)
    if m:
        judgment = re.sub(r"\s+", " ", m.group(1).strip())[:300]

    next_q = ""
    m2 = re.search(r"是否需要下一轮[：:]\s*\n(.+)", raw, re.S)
    if m2:
        next_q = m2.group(1).strip()[:200]

    cp = sections["confirmed_points"][:5] or [f"{guest} round {round_tag(round_num)} 已产出结构化 raw"]
    cf = sections["conflicts"][:3]
    oq = sections["open_questions"][:3]

    cf_lines = [f"- {x}" for x in cf] if cf else ["- (无)"]
    oq_lines = [f"- {x}" for x in oq] if oq else ["- (无)"]
    lines = [
        "### confirmed_points",
        *[f"- {x}" for x in cp],
        "",
        "### conflicts",
        *cf_lines,
        "",
        "### open_questions",
        *oq_lines,
        "",
        "### guest_position_summary",
        judgment or f"{guest}（round {round_tag(round_num)}）已完成发言（summarizer 超时，启发式压缩）",
        "",
        "### suggested_next_question",
        next_q or "复核本轮可证伪条件是否满足",
    ]
    return "\n".join(lines) + "\n"


def merge_unique(existing: list[str], new_items: list[str]) -> list[str]:
    seen = set(existing)
    out = list(existing)
    for item in filter_semantic_items(new_items):
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def run_summarizer_for_guest(
    guests: dict[str, Any],
    *,
    raw_output: str,
    guest_name: str,
    round_num: int,
) -> tuple[str, bool]:
    summarizer_cfg = guests.get("summarizer", {})
    sum_timeout = int(summarizer_cfg.get("timeout_seconds", 120))
    summarizer_prompt = SUMMARIZER_TEMPLATE.read_text(encoding="utf-8")
    summarizer_prompt += "\n\n---\n\n## Guest 原始输出\n\n" + truncate_for_summarizer(raw_output)
    summary_body, sum_mock = invoke_cli(
        summarizer_cfg.get("command", ""),
        summarizer_prompt,
        mock_label="summarizer-cli-missing",
        round_num=round_num,
        guest=guest_name,
        kind="summarizer",
        timeout_seconds=sum_timeout,
    )
    if sum_mock or is_mock_semantic_item(summary_body[:120]):
        summary_body = fallback_summary_from_research_raw(raw_output, guest=guest_name, round_num=round_num)
        sum_mock = False
    return summary_body, sum_mock