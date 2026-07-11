"""Extract concise guest voice from research-format raw output."""

from __future__ import annotations

import re

_VOICE_SECTIONS = ("判断", "已确认事实", "合理推断")
_META_PREFIX = re.compile(
    r"^\s*[-*•]?\s*\[(?:回应\s+\w+|细化\s+\w+|修正\s+\w+|MOCK[^\]]*)\]\s*",
    re.I,
)
_SECTION_BREAK = re.compile(
    r"^(判断|已确认事实|合理推断|市场预期|不确定事项|证据|反方视角|风险|建议|"
    r"claim_responses|是否需要下一轮)\s*[:：]?\s*$",
    re.I | re.M,
)


def _strip_meta(line: str) -> str:
    line = _META_PREFIX.sub("", line.strip())
    return re.sub(r"^\s*[-*•]\s*", "", line).strip()


def _section_slice(text: str, header: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(header)}\s*[:：]?\s*\n(.*?)(?=^(?:判断|已确认事实|合理推断|市场预期|"
        rf"不确定事项|证据|反方视角|风险|建议|claim_responses|是否需要下一轮)\s*[:：]?\s*$|\Z)",
        re.I | re.M | re.S,
    )
    match = pattern.search(text)
    if not match:
        return ""
    lines = [_strip_meta(ln) for ln in match.group(1).splitlines() if ln.strip()]
    return "\n".join(ln for ln in lines if ln)


def extract_guest_voice(raw_text: str) -> str:
    """Return concise spoken judgment for chat bubble (not full structured report)."""
    text = (raw_text or "").strip()
    if not text:
        return ""

    parts: list[str] = []
    judgment = _section_slice(text, "判断")
    if judgment:
        parts.append(judgment)

    # 反方视角 often duplicates obligation filler — only take if no 判断
    if not parts:
        contra = _section_slice(text, "反方视角")
        if contra:
            parts.append(contra)

    if not parts:
        inference = _section_slice(text, "合理推断")
        if inference:
            parts.append(inference)

    if parts:
        voice = "\n".join(parts)
        # Cap length for chat readability
        if len(voice) > 600:
            voice = voice[:597].rstrip() + "…"
        return voice

    # Fallback: first non-empty line that isn't a section header
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _SECTION_BREAK.match(stripped):
            continue
        cleaned = _strip_meta(stripped)
        if cleaned and len(cleaned) > 8:
            return cleaned[:600]

    return text[:400]