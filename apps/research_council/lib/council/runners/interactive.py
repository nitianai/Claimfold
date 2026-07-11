"""Interactive round runner — sequential turn-based guest dialogue."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from council.adapters.meeting_events import (
    meeting_event_log,
    publish_claim_responded,
    publish_guest_completed,
    publish_round_started,
    publish_state_merged,
)
from council.adapters.session_adapter import artifact_paths_research
from council.claims import (
    append_claim_event,
    parse_claim_responses_from_raw,
    rebuild_index,
)
from council.config import CONFIG_FILE, DATA_ROOT
from council.context.market import parse_script_equity_raw
from council.context.service import MeetingContextService, RoundContextSnapshot
from council.formatting import round_tag
from council.guests import guest_roster, is_script_guest, load_guests_for_meeting
from council.interactive.events import (
    publish_context_observed,
    publish_floor_granted,
    publish_floor_yielded,
    publish_message_committed,
    publish_message_proposed,
    publish_session_ended,
    publish_session_paused,
    publish_session_started,
)
from council.interactive.protocol import (
    apply_floor_requests_to_queue,
    apply_pending_interrupts,
    record_message_thread,
    refresh_queue_from_pending_requests,
)
from council.interactive.prompts import append_prior_turns
from council.interactive.state import (
    bump_event_seq,
    ensure_interactive_fields,
    init_round_queue,
    is_interactive_mode,
    pop_next_speaker,
    resolve_max_turns,
    sync_context_cursor,
)
from council.meeting_helpers import (
    ensure_no_overwrite,
    owner_pause_message,
    stop_suggestions,
    update_stop_recommendation,
    write_error_file,
)
from council.mock import generate_mock_research_output
from council.parsers.summary_json import (
    apply_summary_json_to_state,
    build_summary_json,
    summary_json_to_md,
)
from council.parsers import parse_summary_sections, run_summarizer_for_guest
from council.prompts import generate_research_prompt, resolve_selected_guests
from council.selection import load_full_config
from council.state_store import load_state, save_state
from council.verify import verify_research_semantic_loop
from missionos.utils import clamp_int, utc_now

from council.cli_runner import invoke_cli, invoke_script


def process_interactive_guest(
    *,
    meeting_dir: Path,
    state: dict[str, Any],
    guests: dict[str, Any],
    guest_name: str,
    round_num: int,
    snapshot: RoundContextSnapshot,
    prior_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    t0 = time.time()
    paths = artifact_paths_research(meeting_dir, round_num, guest_name, round_tag)
    guest_cfg = guests.get(guest_name, {})
    timeout = clamp_int(guest_cfg.get("timeout_seconds", 180), default=180, min_val=10, max_val=900)
    model_tier = guest_cfg.get("model_tier", "unknown")
    respond_events: list[dict[str, Any]] = []

    try:
        for p in paths.values():
            ensure_no_overwrite(p)

        injected_claims = list(snapshot.prior_claims)
        sum_mock = False

        if is_script_guest(guest_cfg):
            cmd = guest_cfg.get("command", "")
            prompt = f"# Script Guest — {guest_name}\n\ncommand: `{cmd}`\n"
            paths["prompt"].write_text(prompt, encoding="utf-8")
            raw_output, script_ok = invoke_script(cmd, timeout_seconds=timeout)
            raw_mock = not script_ok
            if raw_mock:
                sym = guest_cfg.get("script_symbol", "TSLA")
                raw_output = (
                    f"# Equity Data Feed — {sym}\n\n"
                    f"> 【数据缺失】脚本未成功执行: `{cmd}`\n"
                )
            paths["raw"].write_text(raw_output.strip() + "\n", encoding="utf-8")
            parsed = parse_script_equity_raw(raw_output)
            summary_data = build_summary_json(
                meeting_id=state["meeting_id"],
                round_num=round_num,
                guest=guest_name,
                parsed=parsed,
                raw_text=raw_output,
            )
            raw_mock = raw_mock
        else:
            base_prompt = generate_research_prompt(
                state, guests, guest_name, meeting_dir, snapshot=snapshot
            )
            prompt = append_prior_turns(base_prompt, prior_messages)
            paths["prompt"].write_text(prompt, encoding="utf-8")

            raw_output, raw_mock = invoke_cli(
                guest_cfg.get("command", ""),
                prompt,
                mock_label="guest-cli-missing",
                round_num=round_num,
                guest=guest_name,
                kind="guest",
                timeout_seconds=timeout,
            )
            if raw_mock:
                raw_output = generate_mock_research_output(
                    guest=guest_name,
                    round_num=round_num,
                    label="mock",
                    state=state,
                    injected_claims=injected_claims,
                )
            paths["raw"].write_text(raw_output.strip() + "\n", encoding="utf-8")

            if injected_claims:
                allowed_ids = {c.get("claim_id", "") for c in injected_claims if c.get("claim_id")}
                primary_cid = injected_claims[0].get("claim_id", "")
                raw_rel = f"{meeting_dir.name}/raw/round-{round_tag(round_num)}-{guest_name}.md"
                respond_events = parse_claim_responses_from_raw(
                    raw_output,
                    claim_id=primary_cid,
                    guest=guest_name,
                    meeting_id=state["meeting_id"],
                    meeting_dir=meeting_dir,
                    allowed_claim_ids=allowed_ids,
                    raw_rel_path=raw_rel,
                )

            summary_body, sum_mock = run_summarizer_for_guest(
                guests,
                raw_output=raw_output,
                guest_name=guest_name,
                round_num=round_num,
            )
            parsed = parse_summary_sections(summary_body)
            summary_data = build_summary_json(
                meeting_id=state["meeting_id"],
                round_num=round_num,
                guest=guest_name,
                parsed=parsed,
                raw_text=raw_output,
            )

        paths["summary_json"].write_text(
            json.dumps(summary_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        paths["summary_md"].write_text(summary_json_to_md(summary_data), encoding="utf-8")

        duration = round(time.time() - t0, 1)
        return {
            "guest": guest_name,
            "success": True,
            "summary_data": summary_data,
            "duration_s": duration,
            "used_mock_guest": raw_mock,
            "used_mock_summarizer": sum_mock,
            "claim_responds": len(respond_events),
            "respond_events": respond_events,
            "model_tier": model_tier,
            "guest_type": guest_cfg.get("guest_type", "llm"),
            "prompt_path": str(paths["prompt"].relative_to(meeting_dir)),
            "raw_output_path": str(paths["raw"].relative_to(meeting_dir)),
            "summary_md_path": str(paths["summary_md"].relative_to(meeting_dir)),
            "summary_json_path": str(paths["summary_json"].relative_to(meeting_dir)),
            "round": round_num,
        }
    except Exception as exc:
        duration = round(time.time() - t0, 1)
        err_path = paths.get("error")
        if err_path and not err_path.exists():
            write_error_file(err_path, guest=guest_name, round_num=round_num, error=str(exc))
        return {
            "guest": guest_name,
            "success": False,
            "error": str(exc),
            "duration_s": duration,
            "error_path": str(err_path.relative_to(meeting_dir)) if err_path else "",
            "respond_events": [],
            "round": round_num,
        }


def _begin_interactive_round(
    state: dict[str, Any],
    selected: list[str],
    event_log,
    snapshot_meeting_id: str,
) -> int:
    round_num = int(state.get("interactive_round") or (state["round"] + 1))
    if state.get("session_status") != "active":
        state["interactive_round"] = round_num
        init_round_queue(state, selected)
        apply_pending_interrupts(state)
        merged = apply_floor_requests_to_queue(state, list(state.get("speaking_queue") or []))
        state["speaking_queue"] = merged
        state["floor_requests"] = []
        state["session_status"] = "active"
        seq = bump_event_seq(state)
        publish_session_started(
            event_log,
            round_num=round_num,
            guests=merged,
            interaction_mode=state.get("interaction_mode", "turn_based"),
            event_seq=seq,
        )
        publish_round_started(
            event_log,
            round_num=round_num,
            guests=selected,
            snapshot_meeting_id=snapshot_meeting_id,
        )
    return round_num


def _commit_session_message(
    state: dict[str, Any],
    *,
    guest: str,
    turn: int,
    entry: dict[str, Any],
    reply_to: str | None,
) -> str:
    message_id = f"msg-{round_tag(int(state['interactive_round']))}-{turn:02d}-{guest}"
    excerpt = ""
    summary = entry.get("summary_data") or {}
    if isinstance(summary, dict):
        excerpt = str(summary.get("guest_position_summary", "")).strip()
    state.setdefault("session_messages", []).append(
        {
            "message_id": message_id,
            "guest": guest,
            "turn": turn,
            "reply_to": reply_to,
            "excerpt": excerpt,
        }
    )
    return message_id


def _finalize_interactive_round(
    meeting_dir: Path,
    state: dict[str, Any],
    entries: list[dict[str, Any]],
    selected: list[str],
    event_log,
    *,
    t_round: float,
    quiet: bool,
) -> None:
    round_num = int(state["interactive_round"])
    cp_total = cf_total = oq_total = 0
    for entry in entries:
        if not entry.get("success"):
            continue
        counts = apply_summary_json_to_state(state, entry["summary_data"])
        entry["confirmed_points_added"] = counts["confirmed_points_added"]
        entry["conflicts_added"] = counts["conflicts_added"]
        entry["open_questions_added"] = counts["open_questions_added"]
        cp_total += counts["confirmed_points_added"]
        cf_total += counts["conflicts_added"]
        oq_total += counts["open_questions_added"]

    round_duration = round(time.time() - t_round, 1)
    state["round"] = round_num
    state["round_mode"] = "interactive"
    state["rounds_since_owner"] = state.get("rounds_since_owner", 0) + 1
    state["guest_turns_since_owner"] = state.get("guest_turns_since_owner", 0) + sum(
        1 for e in entries if e.get("success")
    )
    state["history"].append(
        {
            "mode": "interactive",
            "round": round_num,
            "guests": selected,
            "entries": entries,
            "timestamp": utc_now(),
            "duration_s": round_duration,
            "confirmed_points_added": cp_total,
            "conflicts_added": cf_total,
            "open_questions_added": oq_total,
        }
    )
    if state["rounds_since_owner"] >= state.get("max_round_before_owner", 3):
        state["owner_required"] = True

    update_stop_recommendation(state)
    state["session_status"] = "idle"
    state["current_speaker"] = None
    state["interactive_round"] = None
    state["interactive_guests"] = []
    state["interactive_entries"] = []
    state["speaking_queue"] = []
    state["floor_turn"] = 0
    state["session_messages"] = []
    state["guest_build_on"] = {}

    success_count = sum(1 for e in entries if e.get("success"))
    for entry in entries:
        publish_guest_completed(event_log, {**entry, "round": round_num})
    publish_state_merged(
        event_log,
        round_num=round_num,
        confirmed_points_added=cp_total,
        conflicts_added=cf_total,
        open_questions_added=oq_total,
        duration_s=round_duration,
        guest_count=success_count,
    )
    seq = bump_event_seq(state)
    publish_session_ended(
        event_log,
        round_num=round_num,
        guest_count=success_count,
        duration_s=round_duration,
        event_seq=seq,
    )

    if not quiet:
        print(f"\nInteractive round {round_tag(round_num)} done in {round_duration}s")
        suggestions = stop_suggestions(state)
        if suggestions:
            print("\n💡 建议停止条件（非强制，Owner 决定）：")
            for s in suggestions:
                print(f"  - {s}")
        if state["owner_required"]:
            print(owner_pause_message(state))
        else:
            print("Run again: ./council.sh run-interactive")

    if round_num >= 2:
        ok, loop_errors = verify_research_semantic_loop(meeting_dir, round_num=round_num)
        if not ok:
            print("\n⚠️  Research 语义闭环验收失败：")
            for err in loop_errors:
                print(f"  - {err}")
        elif not quiet:
            print(f"\n✓ Research 语义闭环验收通过（round {round_tag(round_num)}）")


def run_interactive_turn(meeting_dir: Path, *, quiet: bool = False) -> tuple[str | None, bool]:
    """Advance one floor turn. Returns (stop_reason, round_finalized)."""
    state = load_state(meeting_dir)
    ensure_interactive_fields(state)

    if state.get("status") == "stopped":
        raise SystemExit("Meeting already stopped.")
    if not is_interactive_mode(state):
        raise SystemExit("Not an interactive meeting. Use: ./council.sh start \"议题\" --mode interactive")
    if state.get("owner_required"):
        print(owner_pause_message(state))
        raise SystemExit(2)
    if state["round"] >= state.get("max_rounds", 12) and state.get("session_status") not in ("active", "paused"):
        return f"已达最大轮次 {state.get('max_rounds', 12)}", False

    guests = load_guests_for_meeting(meeting_dir)
    roster = guest_roster(guests)
    load_full_config(CONFIG_FILE)

    session_status = state.get("session_status", "idle")
    if session_status in ("idle", "ended"):
        selected = resolve_selected_guests(state, guests, roster)
        if not selected:
            raise SystemExit("No guests selected. Run: ./council.sh select <guest>...")
        if not quiet:
            print(f"Interactive session — guests: {', '.join(selected)}")
    else:
        selected = list(state.get("interactive_guests") or [])
        if not selected:
            raise SystemExit("Interactive session state corrupt: missing interactive_guests")

    context_service = MeetingContextService(DATA_ROOT)
    event_log = meeting_event_log(meeting_dir, state.get("meeting_id", meeting_dir.name))

    t_round = time.time()
    if session_status in ("idle", "ended"):
        round_num = _begin_interactive_round(
            state,
            selected,
            event_log,
            snapshot_meeting_id=meeting_dir.name,
        )
    else:
        state["session_status"] = "active"
        round_num = int(state["interactive_round"])
        if refresh_queue_from_pending_requests(state) and not quiet:
            print(f"  Queue updated: {', '.join(state.get('speaking_queue') or [])}")

    snapshot = context_service.snapshot_for_round(meeting_dir, state, round_num=round_num)

    max_turns = resolve_max_turns(state, len(selected))
    if int(state.get("floor_turn") or 0) >= max_turns and state.get("speaking_queue"):
        state["speaking_queue"] = []
        if not quiet:
            print(f"  ⚠ max_turns_per_round={max_turns} reached — truncating queue")

    guest = pop_next_speaker(state)
    if guest is None:
        entries = list(state.get("interactive_entries") or [])
        _finalize_interactive_round(
            meeting_dir, state, entries, selected, event_log, t_round=t_round, quiet=quiet
        )
        sync_context_cursor(meeting_dir, state)
        save_state(meeting_dir, state)
        if state["round"] >= state.get("max_rounds", 12):
            return f"已达最大轮次 {state.get('max_rounds', 12)}", True
        return None, True

    turn = int(state.get("floor_turn") or 0)
    seq = bump_event_seq(state)
    publish_floor_granted(event_log, round_num=round_num, guest=guest, turn=turn, event_seq=seq)

    prior = list(state.get("session_messages") or [])
    reply_to = prior[-1]["message_id"] if prior else None
    build_on_target = (state.get("guest_build_on") or {}).get(guest)
    if build_on_target:
        reply_to = build_on_target

    cursor = sync_context_cursor(meeting_dir, state)
    seq = bump_event_seq(state)
    publish_context_observed(
        event_log,
        round_num=round_num,
        guest=guest,
        context_cursor=cursor,
        event_seq=seq,
    )

    proposed_id = f"prop-{round_tag(round_num)}-{turn:02d}-{guest}"
    seq = bump_event_seq(state)
    publish_message_proposed(
        event_log,
        round_num=round_num,
        guest=guest,
        turn=turn,
        message_id=proposed_id,
        reply_to=reply_to,
        event_seq=seq,
    )

    if not quiet:
        print(f"  Turn {turn}: {guest} speaking…")

    entry = process_interactive_guest(
        meeting_dir=meeting_dir,
        state=state,
        guests=guests,
        guest_name=guest,
        round_num=round_num,
        snapshot=snapshot,
        prior_messages=prior,
    )

    message_id = _commit_session_message(
        state, guest=guest, turn=turn, entry=entry, reply_to=reply_to
    )
    record_message_thread(state, message_id=message_id, guest=guest, reply_to=reply_to)
    seq = bump_event_seq(state)
    publish_message_committed(
        event_log, entry, message_id=message_id, turn=turn, reply_to=reply_to, event_seq=seq
    )
    seq = bump_event_seq(state)
    publish_floor_yielded(event_log, round_num=round_num, guest=guest, turn=turn, event_seq=seq)

    entries = list(state.get("interactive_entries") or [])
    entries.append(entry)
    state["interactive_entries"] = entries

    pending_claim_events: list[dict[str, Any]] = []
    pending_claim_events.extend(entry.get("respond_events", []))
    if pending_claim_events:
        for ev in pending_claim_events:
            if not ev.get("guest"):
                ev = {**ev, "guest": guest}
            append_claim_event(DATA_ROOT, ev)
            publish_claim_responded(event_log, ev)
        rebuild_index(DATA_ROOT)

    if not entry.get("success"):
        if not quiet:
            print(f"  ✗ {guest}: {entry.get('error', 'failed')[:120]}")
        state["session_status"] = "paused"
        seq = bump_event_seq(state)
        publish_session_paused(
            event_log,
            round_num=round_num,
            remaining_queue=list(state.get("speaking_queue") or []),
            event_seq=seq,
        )
        sync_context_cursor(meeting_dir, state)
        save_state(meeting_dir, state)
        raise SystemExit(1)

    if not quiet:
        print(f"  ✓ {guest} {entry.get('duration_s', '?')}s")

    queue_empty = not (state.get("speaking_queue") or [])
    if queue_empty:
        _finalize_interactive_round(
            meeting_dir, state, entries, selected, event_log, t_round=t_round, quiet=quiet
        )
        sync_context_cursor(meeting_dir, state)
        save_state(meeting_dir, state)
        if state["round"] >= state.get("max_rounds", 12):
            return f"已达最大轮次 {state.get('max_rounds', 12)}", True
        return None, True

    state["session_status"] = "paused"
    seq = bump_event_seq(state)
    publish_session_paused(
        event_log,
        round_num=round_num,
        remaining_queue=list(state.get("speaking_queue") or []),
        event_seq=seq,
    )
    sync_context_cursor(meeting_dir, state)
    save_state(meeting_dir, state)
    if not quiet:
        remaining = ", ".join(state.get("speaking_queue") or [])
        print(f"Session paused — remaining: {remaining}")
        print("Continue: ./council.sh session step  (or session resume)")
    return None, False


def run_one_interactive_round(meeting_dir: Path, *, quiet: bool = False) -> str | None:
    """Run interactive round until queue drained or stop condition."""
    while True:
        reason, finalized = run_interactive_turn(meeting_dir, quiet=quiet)
        if reason:
            return reason
        if finalized:
            return None
        # paused mid-round — keep stepping
        state = load_state(meeting_dir)
        if state.get("session_status") == "paused" and state.get("speaking_queue"):
            state["session_status"] = "active"
            save_state(meeting_dir, state)
            continue
        return None