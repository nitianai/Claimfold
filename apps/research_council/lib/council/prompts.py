"""Council: prompts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from council.claims import (
    format_prior_claims_for_prompt,
    select_claims_for_injection,
    validate_injection_text,
)
from council.context.market import read_market_context
from council.context.service import RoundContextSnapshot
from council.selection import select_guests_for_focus

from council.config import (
    DATA_ROOT,
    GUEST_JSON_TEMPLATE,
    GUEST_RESEARCH_TEMPLATE,
    GUEST_TEMPLATE,
    INVESTMENT_AGENDA,
    INVESTMENT_GUEST_TEMPLATE,
    INVESTMENT_REFINE_QUESTIONS,
    investment_question,
)
from council.formatting import format_guest_summaries, format_list, render_template
from council.guests import guest_role_id, is_investment_mode, is_json_mode, is_research_mode
from council.parsers import format_peer_positions


def _require_template(path: Path, *, label: str) -> Path:
    if not path.is_file():
        raise SystemExit(
            f"Required prompt template missing: {label}\n"
            f"  path: {path}\n"
            f"  fix: ./council.sh init  (or restore from prompts/guest/)"
        )
    return path


def guest_template_path(state: dict[str, Any]) -> Path:
    if is_research_mode(state):
        return _require_template(GUEST_RESEARCH_TEMPLATE, label="research guest prompt")
    if is_json_mode(state) and GUEST_JSON_TEMPLATE.exists():
        return GUEST_JSON_TEMPLATE
    if is_investment_mode(state) and INVESTMENT_GUEST_TEMPLATE.exists():
        return INVESTMENT_GUEST_TEMPLATE
    return GUEST_TEMPLATE


def resolve_round_question(state: dict[str, Any], round_num: int, guest_name: str) -> str:
    if is_investment_mode(state):
        agenda = state.get("round_agenda") or INVESTMENT_AGENDA
        if round_num <= len(agenda):
            return investment_question(agenda[round_num - 1]["question"])
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
    state: dict[str, Any],
    guests: dict[str, Any],
    guest_name: str,
    meeting_dir: Path,
    *,
    snapshot: RoundContextSnapshot | None = None,
) -> dict[str, str]:
    ctx_state = snapshot.state if snapshot is not None else state
    question = (
        ctx_state.get("next_question") or ctx_state.get("current_focus") or ctx_state.get("topic", "")
    )
    if snapshot is not None:
        prior = list(snapshot.prior_claims)
        prior_text = snapshot.prior_claims_text
        market_context = snapshot.market_context
    else:
        prior = select_claims_for_injection(ctx_state, DATA_ROOT)
        prior_text = format_prior_claims_for_prompt(prior)
        inject_errors = validate_injection_text(prior_text)
        if inject_errors:
            raise ValueError("prior_claims 注入校验失败: " + "; ".join(inject_errors))
        market_context = read_market_context(meeting_dir)
    return {
        "topic": ctx_state.get("topic", ""),
        "next_question": question,
        "market_context": market_context,
        "prior_claims": prior_text,
        "guest_role": guests.get(guest_name, {}).get("role", guest_name),
        "guest_id": guest_name,
        "role_id": guest_role_id(guests, guest_name),
        "confirmed_points": format_list(ctx_state.get("confirmed_points", [])),
        "conflicts": format_list(ctx_state.get("conflicts", [])),
        "open_questions": format_list(ctx_state.get("open_questions", [])),
        "owner_views": format_list(ctx_state.get("owner_views", []), empty="(无)"),
        "guest_summaries": format_guest_summaries(ctx_state.get("guest_summaries", {})),
        "semantic_obligations": build_research_semantic_obligations(ctx_state, prior_claims=prior),
    }


def generate_research_prompt(
    state: dict[str, Any],
    guests: dict[str, Any],
    guest_name: str,
    meeting_dir: Path,
    *,
    snapshot: RoundContextSnapshot | None = None,
) -> str:
    ctx = build_research_prompt_context(
        state, guests, guest_name, meeting_dir, snapshot=snapshot
    )
    template = _require_template(GUEST_RESEARCH_TEMPLATE, label="research guest prompt")
    return render_template(template, ctx)


def generate_round_prompt(state: dict[str, Any], guests: dict[str, Any], guest_name: str, round_num: int) -> str:
    if is_investment_mode(state):
        state = dict(state)
        state["next_question"] = resolve_round_question(state, round_num, guest_name)
    ctx = build_prompt_context(state, guests, guest_name, round_num)
    return render_template(guest_template_path(state), ctx)


def resolve_selected_guests(state: dict[str, Any], guests: dict[str, Any], roster: list[str]) -> list[str]:
    explicit = state.get("selected_guests") or []
    if explicit:
        return select_guests_for_focus("", roster, guests, explicit=explicit)
    focus = state.get("current_focus") or state.get("next_question") or state.get("topic", "")
    return select_guests_for_focus(focus, roster, guests)

