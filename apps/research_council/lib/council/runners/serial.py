"""Council: serial (one-guest) round execution."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from missionos.utils import strict_cli_enabled, utc_now

from council.cli_runner import invoke_cli
from council.formatting import artifact_paths, round_tag
from council.guests import (
    guest_role_id,
    guest_roster,
    is_investment_mode,
    is_json_mode,
    load_guests_for_meeting,
)
from council.adapters.plan_runtime import advance_plan_speaker, load_state_plan, plan_guest_roster
from council.mock import generate_mock_guest_json
from council.parsers import (
    apply_parsed_summary,
    extract_json_from_text,
    merge_guest_json_into_state,
    parse_summary_sections,
    run_summarizer_for_guest,
    validate_guest_json,
)
from council.state_store import load_state, save_state

from council.meeting_helpers import (
    ensure_no_overwrite,
    owner_pause_message,
    stop_suggestions,
    update_stop_recommendation,
    write_summary_file,
)
from council.prompts import (
    check_investment_auto_stop,
    generate_round_prompt,
    next_guest_name,
    resolve_round_question,
    rotate_guest,
)


def run_one_round(meeting_dir: Path, *, quiet: bool = False) -> str | None:
    """Run one guest turn. Returns auto-stop reason if meeting should end."""
    state = load_state(meeting_dir)
    guests = load_guests_for_meeting(meeting_dir)
    plan = load_state_plan(meeting_dir, state)
    if plan is not None:
        roster = plan_guest_roster(plan, guests)
    else:
        roster = guest_roster(guests, serial=True)

    if state.get("status") == "stopped":
        raise SystemExit("Meeting already stopped. Use ./council.sh start to begin a new one.")

    if state.get("owner_required") and not is_investment_mode(state):
        print(owner_pause_message(state))
        raise SystemExit(2)

    pre_stop = check_investment_auto_stop(state)
    if pre_stop:
        return pre_stop

    if is_investment_mode(state) and state["round"] >= state.get("max_rounds", 100):
        return f"已达最大轮次 {state.get('max_rounds', 100)}"

    guest_name = next_guest_name(state, roster)
    if not guest_name:
        raise SystemExit("No guest available.")

    guest_cfg = guests.get(guest_name, {})
    guest_cmd = guest_cfg.get("command", "")
    role_id = guest_role_id(guests, guest_name)
    json_mode = is_json_mode(state)

    round_num = state["round"] + 1
    paths = artifact_paths(meeting_dir, round_num, guest_name, json_mode=json_mode)
    for p in paths.values():
        ensure_no_overwrite(p)

    if is_investment_mode(state):
        state["next_question"] = resolve_round_question(state, round_num, guest_name)

    focus = state.get("next_question", "")
    prompt = generate_round_prompt(state, guests, guest_name, round_num)
    paths["prompt"].write_text(prompt, encoding="utf-8")

    if not quiet:
        print(f"Round {round_tag(round_num)} — guest: {guest_name} ({role_id})")
        print(f"Focus: {focus[:100]}...")
        print(f"Prompt saved: {paths['prompt']}")

    parsed: dict[str, Any] = {}

    if json_mode:
        raw_output, raw_mock = invoke_cli(
            guest_cmd,
            prompt,
            mock_label="guest-cli-missing",
            round_num=round_num,
            guest=guest_name,
            kind="guest",
        )
        if raw_mock:
            raw_output = generate_mock_guest_json(
                guest=guest_name,
                role_id=role_id,
                round_num=round_num,
                focus=focus,
                label="mock",
            )

        validation_errors: list[str] = []
        try:
            guest_data = extract_json_from_text(raw_output)
            validation_errors = validate_guest_json(
                guest_data, guest_name=guest_name, role_id=role_id, round_num=round_num
            )
            if validation_errors:
                raise ValueError("; ".join(validation_errors))
        except (json.JSONDecodeError, ValueError) as exc:
            validation_errors = validation_errors or [str(exc)]
            if strict_cli_enabled():
                detail = validation_errors[0]
                raise SystemExit(
                    f"STRICT: guest {guest_name} returned invalid JSON — {detail}"
                ) from exc
            guest_data = json.loads(
                generate_mock_guest_json(
                    guest=guest_name,
                    role_id=role_id,
                    round_num=round_num,
                    focus=focus,
                    label=f"invalid-json: {validation_errors[0][:80]}",
                )
            )
            raw_mock = True

        paths["raw"].write_text(json.dumps(guest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not quiet:
            print(f"JSON saved: {paths['raw']}" + (" [MOCK/FIXED]" if raw_mock else ""))
            if validation_errors and not raw_mock:
                print(f"  validation warnings: {validation_errors}")

        counts = merge_guest_json_into_state(state, guest_data)
        history_entry: dict[str, Any] = {
            "round": round_num,
            "guest": guest_name,
            "role": role_id,
            "prompt_path": str(paths["prompt"].relative_to(meeting_dir)),
            "json_path": str(paths["raw"].relative_to(meeting_dir)),
            "timestamp": utc_now(),
            "items_added": counts["items_added"],
            "confidence": guest_data.get("confidence"),
            "position": guest_data.get("position"),
            "used_mock_guest": raw_mock,
            "validation_errors": validation_errors,
        }
    else:
        raw_output, raw_mock = invoke_cli(
            guest_cmd,
            prompt,
            mock_label="guest-cli-missing",
            round_num=round_num,
            guest=guest_name,
            kind="guest",
        )
        paths["raw"].write_text(raw_output.strip() + "\n", encoding="utf-8")
        if not quiet:
            print(f"Raw saved: {paths['raw']}" + (" [MOCK]" if raw_mock else ""))

        summary_body, sum_mock = run_summarizer_for_guest(
            guests,
            raw_output=raw_output,
            guest_name=guest_name,
            round_num=round_num,
        )
        write_summary_file(
            paths["summary"],
            meeting_id=state["meeting_id"],
            round_num=round_num,
            guest=guest_name,
            body=summary_body,
        )
        if not quiet:
            print(f"Summary saved: {paths['summary']}" + (" [MOCK]" if sum_mock else ""))

        parsed = parse_summary_sections(summary_body)
        counts = apply_parsed_summary(state, guest_name, parsed)
        if parsed["suggested_next_question"] and not is_investment_mode(state):
            state["next_question"] = parsed["suggested_next_question"]

        history_entry = {
            "round": round_num,
            "guest": guest_name,
            "prompt_path": str(paths["prompt"].relative_to(meeting_dir)),
            "raw_output_path": str(paths["raw"].relative_to(meeting_dir)),
            "summary_path": str(paths["summary"].relative_to(meeting_dir)),
            "timestamp": utc_now(),
            "confirmed_points_added": counts["confirmed_points_added"],
            "conflicts_added": counts["conflicts_added"],
            "open_questions_added": counts["open_questions_added"],
            "used_mock_guest": raw_mock,
            "used_mock_summarizer": sum_mock,
        }

    state["round"] = round_num
    state["guest_turns_since_owner"] = state.get("guest_turns_since_owner", 0) + 1
    state["rounds_since_owner"] = state.get("rounds_since_owner", 0) + 1
    state["history"].append(history_entry)

    if plan is not None:
        advance_plan_speaker(state)
    else:
        state["next_speaker"] = rotate_guest(guest_name, roster)
    if is_investment_mode(state):
        state["next_question"] = resolve_round_question(state, round_num + 1, state["next_speaker"])
    elif not json_mode and parsed.get("suggested_next_question"):
        state["next_question"] = parsed["suggested_next_question"]

    if not is_investment_mode(state) and state["rounds_since_owner"] >= state.get("max_round_before_owner", 3):
        state["owner_required"] = True

    update_stop_recommendation(state)
    save_state(meeting_dir, state)

    if not quiet:
        suggestions = stop_suggestions(state)
        if suggestions:
            print("\n💡 建议停止条件（非强制，Owner 决定）：")
            for s in suggestions:
                print(f"  - {s}")

        if state["owner_required"]:
            print(owner_pause_message(state))
        else:
            print(f"\nNext speaker: {state['next_speaker']}")
            print("Run again: ./council.sh run")

    return check_investment_auto_stop(state)