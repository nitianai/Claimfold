"""Council: meeting run / parallel / auto commands."""
from __future__ import annotations

import argparse

from council.selection import resolve_guest_alias

from council.formatting import round_tag
from council.guests import guest_roster, is_investment_mode, is_json_mode, load_guests_for_meeting
from council.lifecycle import finish_meeting
from council.prompts import generate_round_prompt, next_guest_name
from council.runners import run_one_interactive_round, run_one_parallel_round, run_one_round
from council.state_store import get_current_meeting_dir, load_state, save_state


def cmd_next(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    guests = load_guests_for_meeting(meeting_dir)
    roster = guest_roster(guests)
    guest_name = next_guest_name(state, roster)
    if not guest_name:
        raise SystemExit("No guest available.")

    preview_round = state["round"] + 1
    prompt = generate_round_prompt(state, guests, guest_name, preview_round)

    print(f"--- Next prompt preview (round {round_tag(preview_round)}, guest: {guest_name}) ---")
    print(prompt)
    print("--- end preview (not saved, models not invoked) ---")


def cmd_run(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    reason = run_one_round(meeting_dir)
    if reason:
        print(f"\n🛑 自动终止条件触发: {reason}")
        finish_meeting(meeting_dir, reason)


def cmd_run_parallel(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    reason = run_one_parallel_round(meeting_dir)
    if reason:
        print(f"\n🛑 自动终止条件触发: {reason}")
        finish_meeting(meeting_dir, reason)


def cmd_run_interactive(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    if state.get("session_status") == "paused":
        state["session_status"] = "active"
        save_state(meeting_dir, state)
    reason = run_one_interactive_round(meeting_dir)
    if reason:
        print(f"\n🛑 自动终止条件触发: {reason}")
        finish_meeting(meeting_dir, reason)


def cmd_select(args: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    guests = load_guests_for_meeting(meeting_dir)
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