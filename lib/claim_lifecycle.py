"""Claim Lifecycle V0.2 — append-only ledger + rebuildable index."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CLAIMS_DIR_NAME = "claims"
LEDGER_FILE = "claims.jsonl"
INDEX_FILE = "claims_index.json"

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


def claims_dir(root: Path) -> Path:
    return root / CLAIMS_DIR_NAME


def ledger_path(root: Path) -> Path:
    return claims_dir(root) / LEDGER_FILE


def index_path(root: Path) -> Path:
    return claims_dir(root) / INDEX_FILE


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_claims_dir(root: Path) -> Path:
    d = claims_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    ledger = ledger_path(root)
    if not ledger.exists():
        ledger.write_text("", encoding="utf-8")
    return d


def load_events(root: Path) -> list[dict[str, Any]]:
    path = ledger_path(root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def append_event(root: Path, event: dict[str, Any]) -> None:
    ensure_claims_dir(root)
    with ledger_path(root).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def next_claim_id(root: Path) -> str:
    events = load_events(root)
    max_n = 0
    for ev in events:
        if ev.get("event") != "PROMOTE":
            continue
        m = re.match(r"clm-(\d+)", ev.get("claim_id", ""))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"clm-{max_n + 1:06d}"


def normalize_statement(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def canonical_scope(scope: dict[str, Any]) -> str:
    return json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_fingerprint(statement: str, scope: dict[str, Any]) -> str:
    payload = normalize_statement(statement) + "|" + canonical_scope(scope)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


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

    if field == "conflicts":
        conflicts = state.get("conflicts", [])
        if index < len(conflicts) and conflicts[index] == text:
            pass
    elif field == "confirmed_points":
        pass
    else:
        errors.append(f"不支持的字段: {field}")

    if not evidence_refs:
        errors.append("evidence_refs 必填")
    else:
        for ref in evidence_refs:
            p = meeting_dir / ref if not ref.startswith("meet-") else Path(ref)
            if not p.exists():
                errors.append(f"证据文件不存在: {ref}")

    return errors


def fold_claims(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    promotes: dict[str, dict[str, Any]] = {}
    for ev in events:
        if ev.get("event") == "PROMOTE" and ev.get("claim_id"):
            promotes[ev["claim_id"]] = dict(ev)

    views: dict[str, dict[str, Any]] = {}
    for claim_id, promo in promotes.items():
        status = "TENTATIVE"
        support_count = 0
        challenge_history: list[dict[str, Any]] = []
        respond_history: list[dict[str, Any]] = []
        last_respond_ts = ""

        for ev in events:
            if ev.get("claim_id") != claim_id:
                continue
            if ev.get("event") == "RETIRE":
                status = "RETIRED"
            elif ev.get("event") == "RESPOND":
                respond_history.append(ev)
                last_respond_ts = ev.get("ts", last_respond_ts)
                if ev.get("response") == "SUPPORT":
                    support_count += 1
                if ev.get("response") == "CHALLENGE":
                    challenge_history.append(ev)
                    if status != "RETIRED":
                        status = "CONTESTED"

        views[claim_id] = {
            "claim_id": claim_id,
            "statement": promo.get("statement", ""),
            "scope": promo.get("scope", {}),
            "fingerprint": promo.get("fingerprint", ""),
            "evidence_refs": promo.get("evidence_refs", []),
            "derived_from_meeting": promo.get("derived_from_meeting", ""),
            "status": status,
            "support_count": support_count,
            "challenge_history": challenge_history,
            "respond_history": respond_history,
            "last_respond_ts": last_respond_ts,
            "promoted_at": promo.get("ts", ""),
        }
    return views


def rebuild_index(root: Path) -> dict[str, Any]:
    events = load_events(root)
    views = fold_claims(events)
    index = {
        "generated_at": utc_now(),
        "claim_count": len(views),
        "claims": views,
    }
    ensure_claims_dir(root)
    index_path(root).write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def load_index(root: Path) -> dict[str, Any]:
    path = index_path(root)
    if not path.exists():
        return rebuild_index(root)
    return json.loads(path.read_text(encoding="utf-8"))


_SUBJECT_ALIASES: dict[str, tuple[str, ...]] = {
    "gold": ("gold", "黄金", "金价", "贵金属"),
    "usd": ("usd", "美元", "dxy", "美元指数"),
    "cny": ("cny", "人民币", "汇率", "cnh"),
    "oil": ("oil", "原油", "石油", "wti", "brent"),
    "btc": ("btc", "比特币", "bitcoin"),
}


def _subject_tokens(subject: str) -> tuple[str, ...]:
    key = subject.strip().lower()
    if key in _SUBJECT_ALIASES:
        return _SUBJECT_ALIASES[key]
    return (key, subject.strip())


def _scope_matches(state: dict[str, Any], scope: dict[str, Any]) -> bool:
    focus = " ".join(
        [
            state.get("current_focus", ""),
            state.get("topic", ""),
            state.get("next_question", ""),
        ]
    ).lower()
    subjects = scope.get("subjects", [])
    if not subjects:
        return True
    for subject in subjects:
        for token in _subject_tokens(str(subject)):
            t = token.lower()
            if t and (t in focus or t in focus.replace("a股", "a")):
                return True
    return False


def _is_stale(scope: dict[str, Any]) -> bool:
    until = scope.get("valid_until")
    if not until:
        return False
    try:
        return datetime.strptime(until, "%Y-%m-%d").date() < datetime.now(timezone.utc).date()
    except ValueError:
        return False


def select_claims_for_injection(
    state: dict[str, Any], root: Path, *, max_k: int = 5
) -> list[dict[str, Any]]:
    index = load_index(root)
    claims = index.get("claims", {})
    picked: list[dict[str, Any]] = []
    for claim_id in sorted(claims.keys()):
        view = claims[claim_id]
        if view.get("status") == "RETIRED":
            continue
        if not _scope_matches(state, view.get("scope", {})):
            continue
        stale = _is_stale(view.get("scope", {}))
        if stale and view.get("status") != "CONTESTED":
            continue
        entry = dict(view)
        entry["stale"] = stale
        picked.append(entry)
    contested = [c for c in picked if c.get("status") == "CONTESTED"]
    tentative = [c for c in picked if c.get("status") == "TENTATIVE"]
    ordered = contested + tentative
    return ordered[:max_k]


def validate_injection_text(text: str) -> list[str]:
    """Check claim lines only — boilerplate disclaimer may negate forbidden words."""
    errors: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ["):
            continue
        for word in FORBIDDEN_INJECT_WORDS:
            if word in stripped:
                errors.append(f"主张行含禁用词: {word}")
    return errors


def format_prior_claims_for_prompt(claims: list[dict[str, Any]]) -> str:
    if not claims:
        return "(无历史试探性主张)"
    lines = [
        "以下内容 **不是事实**，也 **不是当前结论**。",
        "你必须对至少一条选择 SUPPORT | CHALLENGE | RETIRE | DEFER，并写入 claim_responses 段。",
        "",
    ]
    for c in claims:
        status = c.get("status", "TENTATIVE")
        prefix = "[CONTESTED — 优先处理] " if status == "CONTESTED" else ""
        stale = " [STALE]" if c.get("stale") else ""
        scope = c.get("scope", {})
        lines.append(f"- {prefix}[{status}]{stale} {c['claim_id']}: {c.get('statement', '')}")
        lines.append(
            f"  scope: {scope.get('domain', '')} | subjects: {', '.join(scope.get('subjects', []))} "
            f"| valid: {scope.get('valid_from', '')}..{scope.get('valid_until', '')}"
        )
        refs = c.get("evidence_refs", [])
        if refs:
            lines.append(f"  evidence: {', '.join(refs[:3])}")
    return "\n".join(lines)


def parse_claim_responses_from_raw(
    raw_text: str,
    *,
    claim_id: str,
    guest: str,
    meeting_id: str,
    meeting_dir: Path,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    section = ""
    if "claim_responses:" in raw_text.lower():
        idx = raw_text.lower().find("claim_responses:")
        section = raw_text[idx:]
    else:
        for line in raw_text.splitlines():
            if re.search(r"\b(SUPPORT|CHALLENGE|RETIRE|DEFER)\b", line) and "clm-" in line:
                section += line + "\n"

    patterns = [
        r"claim_id:\s*(clm-\d+)\s*\|\s*response:\s*(\w+)\s*\|\s*statement:\s*(.+)",
        r"(clm-\d+)\s*[:：]\s*(SUPPORT|CHALLENGE|RETIRE|DEFER)\s*\|\s*statement:\s*(.+)",
        r"(clm-\d+).*?(SUPPORT|CHALLENGE|RETIRE|DEFER)[:：]\s*(.+)",
    ]
    for line in section.splitlines():
        line = line.strip().lstrip("-*• ")
        if not line or "clm-" not in line:
            continue
        matched = False
        for pat in patterns:
            m = re.search(pat, line, re.I)
            if not m:
                continue
            cid = m.group(1)
            resp = m.group(2).upper()
            stmt = m.group(3).strip()
            if resp not in RESPONSE_TYPES:
                continue
            rel = f"meetings/{meeting_dir.name}/raw/"
            events.append(
                {
                    "event": "RESPOND",
                    "claim_id": cid,
                    "response": resp,
                    "evidence_refs": [f"{meeting_dir.name}/raw/"],
                    "meeting_id": meeting_id,
                    "actor": f"guest:{guest}",
                    "statement": stmt[:500],
                    "ts": utc_now(),
                }
            )
            matched = True
            break
        if not matched and claim_id and claim_id in line:
            for resp in RESPONSE_TYPES:
                if resp in line.upper():
                    events.append(
                        {
                            "event": "RESPOND",
                            "claim_id": claim_id,
                            "response": resp,
                            "evidence_refs": [],
                            "meeting_id": meeting_id,
                            "actor": f"guest:{guest}",
                            "statement": line[:500],
                            "ts": utc_now(),
                        }
                    )
                    break
    return events


def verify_three_meeting_chain(root: Path) -> tuple[bool, list[str]]:
    """Minimal V0.2 acceptance checks on ledger + index."""
    errors: list[str] = []
    events = load_events(root)
    promotes = [e for e in events if e.get("event") == "PROMOTE"]
    responds = [e for e in events if e.get("event") == "RESPOND"]
    retires = [e for e in events if e.get("event") == "RETIRE"]

    if not promotes:
        errors.append("无 PROMOTE 事件")
    if not index_path(root).exists():
        errors.append("claims_index.json 不存在")

    index = load_index(root)
    if promotes:
        cid = promotes[0]["claim_id"]
        view = index.get("claims", {}).get(cid)
        if not view:
            errors.append(f"index 缺少 {cid}")
        else:
            if responds and view.get("status") not in ("CONTESTED", "RETIRED"):
                errors.append("有 CHALLENGE 回应但 status 未折叠为 CONTESTED")
            if retires and view.get("status") != "RETIRED":
                errors.append("有 RETIRE 但 status 未为 RETIRED")

    return len(errors) == 0, errors