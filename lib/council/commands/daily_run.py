"""Council: run-daily command."""
from __future__ import annotations

import argparse
from datetime import datetime

from runtime_ext import resolve_guest_alias

from council.config import DAILY_DEFAULT_GUESTS, MEETINGS_DIR
from council.daily import build_daily_context, find_latest_prior_final, generate_daily_decision_md
from council.guests import guest_roster, load_guests
from council.runners import run_one_parallel_round
from council.state_store import get_current_meeting_dir, load_state, save_state
from utils import resolve_meeting_path, utc_now


def cmd_run_daily(args: argparse.Namespace) -> None:
    """14:30 日频：昨日盘后 + 今日脚本 → 并行嘉宾 → daily_decision.md"""
    scope = (args.scope or "").strip()
    if not scope:
        raise SystemExit("Usage: ./council.sh run-daily \"TSLA、VIX、美债\"")

    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    guests = load_guests()
    roster = guest_roster(guests)

    if state.get("status") == "stopped":
        raise SystemExit("Meeting stopped. Start a new research meeting first.")

    if state.get("owner_required"):
        if not args.force_owner_continue:
            raise SystemExit(
                "owner_required is set. Run ./council.sh continue first, "
                "or pass --force-owner-continue for 14:30 daily automation."
            )
        state["owner_required"] = False
        state["guest_turns_since_owner"] = 0
        state["rounds_since_owner"] = 0
        state["daily_owner_override"] = {
            "ts": utc_now(),
            "reason": "run-daily --force-owner-continue",
        }
        print("Auto-continue: owner_required cleared for daily run (audited).")

    prior = None
    if args.prior_meeting:
        candidate = resolve_meeting_path(MEETINGS_DIR, args.prior_meeting.strip())
        prior = candidate / "final.md"
        if not prior.exists():
            raise SystemExit(f"Prior final.md not found: {prior}")
    else:
        prior = find_latest_prior_final(MEETINGS_DIR, exclude_meeting_id=state.get("meeting_id", ""))

    print(f"=== run-daily @ {datetime.now().strftime('%H:%M:%S')} ===")
    build_daily_context(
        meeting_dir,
        state,
        scope,
        skip_llm=args.skip_context_llm,
        prior_final=prior,
    )

    names = [g.strip() for g in (args.guests or ",".join(DAILY_DEFAULT_GUESTS)).split(",") if g.strip()]
    selected: list[str] = []
    for name in names:
        resolved = resolve_guest_alias(name, roster)
        if not resolved:
            raise SystemExit(f"Unknown guest: {name}")
        if resolved not in selected:
            selected.append(resolved)

    state["selected_guests"] = selected
    state["current_focus"] = scope
    state["next_question"] = f"14:30 日频决策：{scope}"
    save_state(meeting_dir, state)
    print(f"Daily guests: {', '.join(selected)}")

    reason = run_one_parallel_round(meeting_dir, quiet=False)
    state = load_state(meeting_dir)
    round_num = state["round"]

    decision_path = meeting_dir / "daily_decision.md"
    decision_path.write_text(generate_daily_decision_md(state, meeting_dir, round_num), encoding="utf-8")
    print(f"\nDaily decision draft: {decision_path}")

    if reason:
        print(f"Stop signal: {reason}")