"""Claim（主张）晋升策略与证据校验 — App 领域逻辑。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

NON_PROMOTION_MARKERS = (
    "[MOCK]",
    "forced-mock",
    "数据缺失",
    "待复核",
    "模拟",
)

FORBIDDEN_INJECT_WORDS = (
    "已验证",
    "确定",
    "结论",
    "已知",
    "事实",
    "共识",
    "权威判断",
    "系统认为",
    "已经证明",
)

RESPONSE_TYPES = frozenset({"SUPPORT", "CHALLENGE", "RETIRE", "DEFER"})

ALLOWED_EVIDENCE_DIRS = frozenset({"raw", "summaries", "context"})


def validate_scope(scope: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not scope.get("domain"):
        errors.append("scope.domain 必填")
    if not scope.get("subjects"):
        errors.append("scope.subjects 必填")
    has_boundary = bool(
        scope.get("valid_until")
        or scope.get("conditions")
        or scope.get("regime_tags")
    )
    if not has_boundary:
        errors.append("scope 需至少一种边界：valid_until / conditions / regime_tags")
    return errors


def _strip_speaker_prefix(statement: str) -> str:
    return re.sub(r"^\[[^\]]+\]\s*", "", (statement or "").strip(), count=1)


def _normalize_for_anchor(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _statement_anchor(statement: str, *, min_len: int = 12) -> str:
    cleaned = re.sub(r"\s+", " ", (statement or "").strip())
    if len(cleaned) < min_len:
        return cleaned.lower()
    return cleaned[: min(80, len(cleaned))].lower()


def _resolve_evidence_file(ref: str, *, meeting_dir: Path) -> tuple[Path | None, str | None]:
    rel = (ref or "").strip()
    if not rel:
        return None, "证据路径为空"

    meeting_name = meeting_dir.name
    if rel.startswith(f"{meeting_name}/"):
        rel = rel[len(meeting_name) + 1 :]

    if rel.startswith(("/", "\\")):
        return None, f"证据路径必须为相对路径: {ref}"

    pure = Path(rel)
    if pure.is_absolute():
        return None, f"证据路径必须为相对路径: {ref}"

    parts = pure.parts
    if not parts or parts[0] not in ALLOWED_EVIDENCE_DIRS:
        return None, f"证据路径不在允许目录 raw/summaries/context: {ref}"
    if any(part == ".." for part in parts):
        return None, f"证据路径禁止目录穿越: {ref}"

    meeting_root = meeting_dir.resolve()
    candidate = (meeting_root / pure).resolve()
    try:
        candidate.relative_to(meeting_root)
    except ValueError:
        return None, f"证据路径越界: {ref}"

    allowed_root = (meeting_root / parts[0]).resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError:
        return None, f"证据路径不在允许目录 raw/summaries/context: {ref}"

    if not candidate.exists():
        return None, f"证据文件不存在: {ref}"
    if not candidate.is_file():
        return None, f"证据路径必须是文件: {ref}"
    return candidate, None


def validate_promotion_candidate(
    *,
    statement: str,
    evidence_refs: list[str],
    meeting_dir: Path,
    state: dict[str, Any],
    field: str,
    index: int,
) -> list[str]:
    errors: list[str] = []
    text = (statement or "").strip()
    if not text:
        return ["statement 为空"]

    for marker in NON_PROMOTION_MARKERS:
        if marker.lower() in text.lower():
            errors.append(f"命中禁止晋升标记: {marker}")

    if field == "open_questions":
        errors.append("open_questions 不能晋升为主张")

    if field not in ("conflicts", "confirmed_points"):
        errors.append(f"不支持的字段: {field}")

    if field == "confirmed_points":
        active_conflicts = [str(c).strip() for c in state.get("conflicts", [])]
        if text in active_conflicts:
            errors.append("陈述仍存在于活跃 conflicts，不可从 confirmed_points 晋升")

    history = state.get("history", [])
    if len(history) <= 1:
        guest_count = 0
        if history:
            h = history[0]
            if h.get("mode") == "parallel":
                guest_count = len(h.get("guests", []))
            else:
                guest_count = 1
        if guest_count <= 1:
            errors.append("单轮单 Guest 无 RESPOND 链（single-round singleton），默认拒绝晋升")

    if not evidence_refs:
        errors.append("evidence_refs 必填")
    else:
        anchor = _statement_anchor(_strip_speaker_prefix(text))
        norm_anchor = _normalize_for_anchor(anchor)
        anchored = False
        read_any = False
        has_raw_evidence = False
        for ref in evidence_refs:
            rel = (ref or "").strip()
            meeting_name = meeting_dir.name
            if rel.startswith(f"{meeting_name}/"):
                rel = rel[len(meeting_name) + 1 :]
            if rel.startswith("raw/"):
                has_raw_evidence = True
            p, path_error = _resolve_evidence_file(ref, meeting_dir=meeting_dir)
            if path_error:
                errors.append(path_error)
                continue
            assert p is not None
            try:
                content = p.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"无法读取证据文件 {ref}: {exc}")
                continue
            read_any = True
            if norm_anchor and norm_anchor in _normalize_for_anchor(content):
                anchored = True
        if not has_raw_evidence:
            errors.append("须至少引用一条 raw/ 证据（summaries/ 或 context/ 不能单独成立）")
        if read_any and not anchored and norm_anchor:
            errors.append("证据 raw 中未找到陈述锚点（statement anchor）")

    return errors