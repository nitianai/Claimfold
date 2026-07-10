"""Council: meeting owner / status commands."""
from __future__ import annotations

import argparse
import json

from council.formatting import format_guest_summaries, format_list
from council.guests import is_json_mode
from council.lifecycle import finish_meeting
from council.meeting_helpers import stop_suggestions
from council.state_store import get_current_meeting_dir, load_state, save_state


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


def cmd_stop(_: argparse.Namespace) -> None:
    finish_meeting(get_current_meeting_dir(), "manual stop by owner")


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