"""Interactive session CLI — inspect / step / resume."""

from __future__ import annotations

import argparse
import json

from council.interactive.state import ensure_interactive_fields, is_interactive_mode, session_inspect_payload
from council.interactive.annotations import build_session_annotations
from council.runners.interactive import run_interactive_turn, run_one_interactive_round
from council.state_store import get_current_meeting_dir, load_state, save_state
from missionos.session.events import load_session_events


def cmd_session_inspect(args: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    ensure_interactive_fields(state)
    payload = session_inspect_payload(state)
    if getattr(args, "annotations", False):
        payload["annotations"] = build_session_annotations(meeting_dir, state)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_session_replay(args: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    ensure_interactive_fields(state)
    events = load_session_events(meeting_dir)
    cursor = int(state.get("context_cursor") or 0)
    start = max(0, cursor - int(getattr(args, "tail", 20) or 20))
    for ev in events[start:]:
        print(json.dumps(ev, ensure_ascii=False))
    print(f"--- replay {start}..{len(events)} (context_cursor={cursor}) ---")


def cmd_session_step(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    if not is_interactive_mode(state):
        raise SystemExit("Not an interactive meeting.")
    if state.get("session_status") == "paused":
        state["session_status"] = "active"
        save_state(meeting_dir, state)
    run_interactive_turn(meeting_dir)


def cmd_session(args: argparse.Namespace) -> None:
    handlers = {
        "inspect": cmd_session_inspect,
        "step": cmd_session_step,
        "resume": cmd_session_resume,
        "replay": cmd_session_replay,
    }
    handler = handlers.get(getattr(args, "session_cmd", ""))
    if not handler:
        raise SystemExit(f"Unknown session subcommand: {getattr(args, 'session_cmd', '')}")
    handler(args)


def cmd_session_resume(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    if not is_interactive_mode(state):
        raise SystemExit("Not an interactive meeting.")
    status = state.get("session_status", "idle")
    if status in ("idle", "ended"):
        raise SystemExit("No paused interactive session. Run: ./council.sh run-interactive")
    state["session_status"] = "active"
    save_state(meeting_dir, state)
    reason = run_one_interactive_round(meeting_dir)
    if reason:
        from council.lifecycle import finish_meeting

        print(f"\n🛑 自动终止条件触发: {reason}")
        finish_meeting(meeting_dir, reason)