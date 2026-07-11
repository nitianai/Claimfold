"""Floor protocol CLI — request / yield / interrupt."""

from __future__ import annotations

import argparse

from council.adapters.meeting_events import meeting_event_log
from council.interactive.events import publish_floor_requested, publish_interrupt_requested
from council.interactive.protocol import register_floor_request, register_interrupt, yield_floor
from council.interactive.state import bump_event_seq, ensure_interactive_fields, is_interactive_mode, sync_context_cursor
from council.state_store import get_current_meeting_dir, load_state, save_state


def cmd_floor_request(args: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    ensure_interactive_fields(state)
    if not is_interactive_mode(state):
        raise SystemExit("Floor protocol requires interactive meeting mode.")

    guest = args.guest.strip()
    if not guest:
        raise SystemExit("Guest id required.")

    round_num = int(state.get("interactive_round") or state.get("round", 0) + 1)
    build_on = args.build_on.strip() if args.build_on else None
    register_floor_request(
        state,
        guest=guest,
        urgency=args.urgency,
        build_on=build_on,
        request_type=args.type.upper(),
    )
    event_log = meeting_event_log(meeting_dir, state.get("meeting_id", meeting_dir.name))
    seq = bump_event_seq(state)
    publish_floor_requested(
        event_log,
        round_num=round_num,
        guest=guest,
        urgency=args.urgency,
        build_on=build_on,
        request_type=args.type.upper(),
        event_seq=seq,
    )
    sync_context_cursor(meeting_dir, state)
    save_state(meeting_dir, state)
    print(f"Floor requested: {guest} urgency={args.urgency}" + (f" build_on={build_on}" if build_on else ""))


def cmd_floor_yield(args: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    ensure_interactive_fields(state)
    guest = args.guest.strip()
    if not yield_floor(state, guest):
        raise SystemExit(f"{guest} does not hold the floor.")
    sync_context_cursor(meeting_dir, state)
    save_state(meeting_dir, state)
    print(f"Floor yielded: {guest}")


def cmd_floor_interrupt(args: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    ensure_interactive_fields(state)
    if not is_interactive_mode(state):
        raise SystemExit("Floor protocol requires interactive meeting mode.")

    guest = args.guest.strip()
    target = args.target.strip()
    target_msg = args.message.strip() if args.message else None
    round_num = int(state.get("interactive_round") or state.get("round", 0) + 1)
    register_interrupt(state, guest=guest, target_guest=target, target_message_id=target_msg)
    event_log = meeting_event_log(meeting_dir, state.get("meeting_id", meeting_dir.name))
    seq = bump_event_seq(state)
    publish_interrupt_requested(
        event_log,
        round_num=round_num,
        guest=guest,
        target_guest=target,
        target_message_id=target_msg,
        event_seq=seq,
    )
    sync_context_cursor(meeting_dir, state)
    save_state(meeting_dir, state)
    print(f"Interrupt requested: {guest} → {target}")


def cmd_floor(args: argparse.Namespace) -> None:
    handlers = {
        "request": cmd_floor_request,
        "yield": cmd_floor_yield,
        "interrupt": cmd_floor_interrupt,
    }
    handler = handlers.get(getattr(args, "floor_cmd", ""))
    if not handler:
        raise SystemExit(f"Unknown floor subcommand: {getattr(args, 'floor_cmd', '')}")
    handler(args)