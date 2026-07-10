"""Council: meeting start command."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from council.config import (
    CURRENT_MEETING_FILE,
    INVESTMENT_AGENDA,
    MEETING_PLAN_FILENAME,
    MEETINGS_DIR,
    investment_question,
)
from council.guests import guest_roster, load_guests, resolve_executor_to_guest
from council.plan import (
    PlanValidationError,
    atomic_write_plan,
    build_meeting_plan,
    first_stage_binding,
    parse_cli_bindings,
)
from council.state_store import save_state


def _validate_start_flags(args: argparse.Namespace) -> None:
    scenario = getattr(args, "scenario", None)
    bindings = getattr(args, "bindings", None)
    bind = getattr(args, "bind", None)
    if bindings and not scenario:
        raise SystemExit("--bindings requires --scenario")
    if bind and not scenario:
        raise SystemExit("--bind requires --scenario")


def _scenario_start_state(
    *,
    meeting_id: str,
    topic: str,
    owner_question: str,
    plan: dict[str, Any],
    meeting_mode: str,
    owner_pause: int,
    max_rounds: int,
    stale_limit: int,
    roster: list[str],
) -> dict[str, Any]:
    first_role_id, first_executor_id = first_stage_binding(plan)
    try:
        first_speaker = resolve_executor_to_guest(first_executor_id, roster)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    participant_ids = [p["participant_id"] for p in plan["participants"]]
    return {
        "meeting_id": meeting_id,
        "topic": topic,
        "owner_question": owner_question,
        "meeting_mode": meeting_mode,
        "scenario_id": plan["scenario"]["id"],
        "meeting_plan_file": MEETING_PLAN_FILENAME,
        "plan_schema_version": plan["schema_version"],
        "participant_ids": participant_ids,
        "next_role_id": first_role_id,
        "next_executor_id": first_executor_id,
        "round": 0,
        "status": "running",
        "owner_required": False,
        "max_round_before_owner": owner_pause,
        "max_rounds": max_rounds,
        "stale_round_limit": stale_limit,
        "guest_turns_since_owner": 0,
        "rounds_since_owner": 0,
        "confirmed_points": [],
        "conflicts": [],
        "open_questions": [],
        "guest_summaries": {},
        "owner_views": [],
        "next_speaker": first_speaker,
        "next_question": owner_question,
        "history": [],
        "stop_reason": "",
        "output_format": "json",
        "round_mode": "serial",
        "selected_guests": [],
        "current_focus": "",
        "stop_recommendation": "",
        "positions": {},
        "challenges": [],
        "verifications": [],
        "round_records": [],
    }


def _legacy_start_state(
    *,
    meeting_id: str,
    topic: str,
    owner_question: str,
    meeting_mode: str,
    owner_pause: int,
    max_rounds: int,
    stale_limit: int,
    roster: list[str],
) -> dict[str, Any]:
    output_format = "json"
    round_mode = "serial"
    if meeting_mode == "research":
        output_format = "research"
        round_mode = "parallel"

    state: dict[str, Any] = {
        "meeting_id": meeting_id,
        "topic": topic,
        "owner_question": owner_question,
        "meeting_mode": meeting_mode,
        "round": 0,
        "status": "running",
        "owner_required": False,
        "max_round_before_owner": owner_pause,
        "max_rounds": max_rounds,
        "stale_round_limit": stale_limit,
        "guest_turns_since_owner": 0,
        "rounds_since_owner": 0,
        "confirmed_points": [],
        "conflicts": [],
        "open_questions": [],
        "guest_summaries": {},
        "owner_views": [],
        "next_speaker": roster[0],
        "next_question": owner_question,
        "history": [],
        "stop_reason": "",
        "output_format": output_format,
        "round_mode": round_mode,
        "selected_guests": [],
        "current_focus": "",
        "stop_recommendation": "",
        "positions": {},
        "challenges": [],
        "verifications": [],
        "round_records": [],
    }
    if meeting_mode == "investment":
        state["round_agenda"] = INVESTMENT_AGENDA
        state["next_question"] = investment_question(INVESTMENT_AGENDA[0]["question"])
        if INVESTMENT_AGENDA[0]["guest"] in roster:
            state["next_speaker"] = INVESTMENT_AGENDA[0]["guest"]
    return state


def cmd_start(args: argparse.Namespace) -> None:
    topic = args.topic.strip()
    if not topic:
        raise SystemExit("Topic cannot be empty.")

    _validate_start_flags(args)

    MEETINGS_DIR.mkdir(parents=True, exist_ok=True)

    meeting_id = datetime.now().strftime("meet-%Y%m%d-%H%M%S")
    meeting_dir = MEETINGS_DIR / meeting_id
    for sub in ("prompts", "raw", "summaries", "errors", "context"):
        (meeting_dir / sub).mkdir(parents=True, exist_ok=False)

    owner_question = args.question.strip() if args.question else topic
    meeting_mode = getattr(args, "mode", "standard") or "standard"
    owner_pause = args.rounds_before_owner
    if owner_pause < 1:
        raise SystemExit("--rounds-before-owner must be >= 1")

    if args.max_rounds is not None:
        max_rounds = args.max_rounds
    elif meeting_mode == "investment":
        max_rounds = 100
    else:
        max_rounds = 12

    stale_limit = getattr(args, "stale_limit", 5)
    scenario = getattr(args, "scenario", None)

    if scenario:
        guests = load_guests()
        roster = guest_roster(guests)
        if not roster:
            raise SystemExit("No enabled guests found in config/guests.yaml")
        try:
            cli_bindings = parse_cli_bindings(getattr(args, "bind", None))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            plan = build_meeting_plan(
                scenario=scenario,
                meeting_id=meeting_id,
                topic=topic,
                generated_at=generated_at,
                bindings_path=getattr(args, "bindings", None),
                cli_bindings=cli_bindings or None,
            )
        except PlanValidationError as exc:
            raise SystemExit(str(exc)) from exc
        plan_path = meeting_dir / MEETING_PLAN_FILENAME
        atomic_write_plan(plan_path, plan)
        state = _scenario_start_state(
            meeting_id=meeting_id,
            topic=topic,
            owner_question=owner_question,
            plan=plan,
            meeting_mode=meeting_mode,
            owner_pause=owner_pause,
            max_rounds=max_rounds,
            stale_limit=stale_limit,
            roster=roster,
        )
    else:
        guests = load_guests()
        roster = guest_roster(guests)
        if not roster:
            raise SystemExit("No enabled guests found in config/guests.yaml")
        state = _legacy_start_state(
            meeting_id=meeting_id,
            topic=topic,
            owner_question=owner_question,
            meeting_mode=meeting_mode,
            owner_pause=owner_pause,
            max_rounds=max_rounds,
            stale_limit=stale_limit,
            roster=roster,
        )

    save_state(meeting_dir, state)
    CURRENT_MEETING_FILE.write_text(meeting_id + "\n", encoding="utf-8")

    print(f"Meeting started: {meeting_id}")
    print(f"Topic: {topic}")
    if scenario:
        print(f"Scenario: {state['scenario_id']}")
        print(f"Plan: {meeting_dir / MEETING_PLAN_FILENAME}")
        print(f"Participants: {len(state['participant_ids'])}")
        print(f"Mode: {meeting_mode} (legacy runner until PR3)")
    else:
        print(f"Mode: {meeting_mode}")
    if meeting_mode == "investment" and not scenario:
        print(f"Max rounds: {state['max_rounds']} | Stale limit: {state['stale_round_limit']}")
        print("Roles: qwen=宏观 | laguna=地缘政策 | north=大宗 | mimo=股票 | nemo=利率外汇")
    elif meeting_mode == "research" and not scenario:
        print(f"Mode: research (parallel) | Max rounds: {state['max_rounds']}")
        print(f"Rounds before owner pause: {owner_pause}")
        print("Next: ./council.sh context \"范围\" && ./council.sh select ... && ./council.sh run-parallel")
    elif not scenario:
        print(f"Rounds before owner pause: {owner_pause} | Max rounds: {state['max_rounds']}")
    print(f"Directory: {meeting_dir}")
    print(f"First speaker: {state['next_speaker']}")
    if scenario:
        print("Next: ./council.sh run  (PR3 will read meeting_plan.json)")
    elif meeting_mode == "investment":
        print("Next: ./council.sh run-auto")
    elif meeting_mode == "research":
        pass
    else:
        print("Next: ./council.sh run  (or run-parallel for research runtime)")