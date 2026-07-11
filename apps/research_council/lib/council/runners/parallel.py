"""Council: parallel round execution."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from council.claims import (
    append_claim_event,
    parse_claim_responses_from_raw,
    rebuild_index,
)
from council.adapters.meeting_events import (
    meeting_event_log,
    publish_claim_responded,
    publish_guest_completed,
    publish_round_started,
    publish_state_merged,
)
from council.adapters.session_adapter import artifact_paths_research
from council.context.market import parse_script_equity_raw
from council.context.service import MeetingContextService, RoundContextSnapshot
from council.parsers.summary_json import (
    apply_summary_json_to_state,
    build_summary_json,
    summary_json_to_md,
)
from council.selection import load_full_config, max_parallel_from_config
from council.verify import verify_research_semantic_loop
from missionos.utils import clamp_int, utc_now

from council.cli_runner import invoke_cli, invoke_script
from council.config import CONFIG_FILE, DATA_ROOT
from council.formatting import round_tag
from council.guests import guest_roster, is_script_guest, load_guests_for_meeting
from council.mock import generate_mock_research_output
from council.parsers import parse_summary_sections, run_summarizer_for_guest
from council.slots import apply_guest_slots_projection, begin_guest_slot, finalize_guest_slot
from council.state_store import load_state, save_state

from council.meeting_helpers import (
    ensure_no_overwrite,
    owner_pause_message,
    stop_suggestions,
    update_stop_recommendation,
    write_error_file,
)
from council.prompts import generate_research_prompt, resolve_selected_guests


def process_parallel_guest(
    *,
    meeting_dir: Path,
    state: dict[str, Any],
    guests: dict[str, Any],
    guest_name: str,
    round_num: int,
    snapshot: RoundContextSnapshot,
) -> dict[str, Any]:
    t0 = time.time()
    paths = artifact_paths_research(meeting_dir, round_num, guest_name, round_tag)
    guest_cfg = guests.get(guest_name, {})
    timeout = clamp_int(guest_cfg.get("timeout_seconds", 180), default=180, min_val=10, max_val=900)
    model_tier = guest_cfg.get("model_tier", "unknown")

    try:
        for p in paths.values():
            ensure_no_overwrite(p)

        injected_claims = list(snapshot.prior_claims)
        respond_events: list[dict[str, Any]] = []
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
        else:
            prompt = generate_research_prompt(
                state, guests, guest_name, meeting_dir, snapshot=snapshot
            )
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

        paths["summary_json"].write_text(json.dumps(summary_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
        }


def require_parallel_success(entries: list[dict[str, Any]], *, quiet: bool = False) -> None:
    """Abort the round when every parallel guest entry failed."""
    success_count = sum(1 for e in entries if e.get("success"))
    if success_count == 0:
        if not quiet:
            print("✗ 并行轮全部失败 — 保留轮次与 selected_guests，未写入 state")
        raise SystemExit(1)


def run_one_parallel_round(meeting_dir: Path, *, quiet: bool = False) -> str | None:
    """Run one parallel round with selected_guests. Returns stop reason if needed."""
    state = load_state(meeting_dir)
    guests = load_guests_for_meeting(meeting_dir)
    roster = guest_roster(guests)
    full_cfg = load_full_config(CONFIG_FILE)
    max_workers = max_parallel_from_config(full_cfg)

    if state.get("status") == "stopped":
        raise SystemExit("Meeting already stopped.")

    if state.get("owner_required"):
        print(owner_pause_message(state))
        raise SystemExit(2)

    if state["round"] >= state.get("max_rounds", 12):
        return f"已达最大轮次 {state.get('max_rounds', 12)}"

    round_num = state["round"] + 1
    selected = resolve_selected_guests(state, guests, roster)
    if not selected:
        raise SystemExit("No guests selected for parallel round.")

    parallel_batch = [g for g in selected if guests.get(g, {}).get("allow_parallel", True)]
    serial_batch = [g for g in selected if not guests.get(g, {}).get("allow_parallel", True)]

    if not quiet:
        print(f"Round {round_tag(round_num)} — parallel guests: {', '.join(selected)}")
        print(f"max_parallel={max_workers} | parallel={len(parallel_batch)} serial={len(serial_batch)}")

    t_round = time.time()
    entries: list[dict[str, Any]] = []
    context_service = MeetingContextService(DATA_ROOT)
    snapshot = context_service.snapshot_for_round(meeting_dir, state, round_num=round_num)
    event_log = meeting_event_log(meeting_dir, state.get("meeting_id", meeting_dir.name))
    publish_round_started(
        event_log,
        round_num=round_num,
        guests=selected,
        snapshot_meeting_id=snapshot.meeting_id,
    )

    def run_guest(guest_name: str) -> dict[str, Any]:
        attempts = begin_guest_slot(event_log, round_num=round_num, guest_id=guest_name)
        entry = process_parallel_guest(
            meeting_dir=meeting_dir,
            state=state,
            guests=guests,
            guest_name=guest_name,
            round_num=round_num,
            snapshot=snapshot,
        )
        finalize_guest_slot(
            event_log,
            round_num=round_num,
            guest_id=guest_name,
            entry=entry,
            attempts=attempts,
        )
        return entry

    if parallel_batch:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(parallel_batch))) as pool:
            futures = {pool.submit(run_guest, g): g for g in parallel_batch}
            for fut in as_completed(futures):
                entries.append(fut.result())
    for guest_name in serial_batch:
        entries.append(run_guest(guest_name))

    entries.sort(key=lambda e: selected.index(e["guest"]) if e["guest"] in selected else 999)

    require_parallel_success(entries, quiet=quiet)

    pending_claim_events: list[dict[str, Any]] = []
    for entry in entries:
        pending_claim_events.extend(entry.get("respond_events", []))
    if pending_claim_events:
        for ev in pending_claim_events:
            append_claim_event(DATA_ROOT, ev)
            publish_claim_responded(event_log, ev)
        rebuild_index(DATA_ROOT)

    cp_total = cf_total = oq_total = 0
    for entry in entries:
        if not entry.get("success"):
            if not quiet:
                print(f"  ✗ {entry['guest']}: {entry.get('error', 'failed')[:120]}")
            continue
        try:
            counts = apply_summary_json_to_state(state, entry["summary_data"])
            entry["confirmed_points_added"] = counts["confirmed_points_added"]
            entry["conflicts_added"] = counts["conflicts_added"]
            entry["open_questions_added"] = counts["open_questions_added"]
            cp_total += counts["confirmed_points_added"]
            cf_total += counts["conflicts_added"]
            oq_total += counts["open_questions_added"]
            if not quiet:
                print(
                    f"  ✓ {entry['guest']} (+cp:{counts['confirmed_points_added']} "
                    f"+cf:{counts['conflicts_added']} +oq:{counts['open_questions_added']}) "
                    f"{entry.get('duration_s', '?')}s"
                )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            entry["success"] = False
            entry["parse_error"] = str(exc)
            err_paths = artifact_paths_research(meeting_dir, round_num, entry["guest"], round_tag)
            if not err_paths["error"].exists():
                write_error_file(
                    err_paths["error"],
                    guest=entry["guest"],
                    round_num=round_num,
                    error=f"summary.json apply failed: {exc}",
                )
            if not quiet:
                print(f"  ✗ {entry['guest']}: summary.json parse failed — state not updated")

    round_duration = round(time.time() - t_round, 1)
    state["round"] = round_num
    state["round_mode"] = "parallel"
    state["rounds_since_owner"] = state.get("rounds_since_owner", 0) + 1
    state["guest_turns_since_owner"] = state.get("guest_turns_since_owner", 0) + sum(
        1 for e in entries if e.get("success")
    )
    state["selected_guests"] = []
    state["history"].append(
        {
            "mode": "parallel",
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
    apply_guest_slots_projection(meeting_dir, state)
    save_state(meeting_dir, state)

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

    if round_num >= 2:
        ok, loop_errors = verify_research_semantic_loop(meeting_dir, round_num=round_num)
        if not ok:
            print("\n⚠️  Research 语义闭环验收失败：")
            for err in loop_errors:
                print(f"  - {err}")
        elif not quiet:
            print(f"\n✓ Research 语义闭环验收通过（round {round_tag(round_num)}）")

    if not quiet:
        print(f"\nRound {round_tag(round_num)} done in {round_duration}s")
        suggestions = stop_suggestions(state)
        if suggestions:
            print("\n💡 建议停止条件（非强制，Owner 决定）：")
            for s in suggestions:
                print(f"  - {s}")
        if state["owner_required"]:
            print(owner_pause_message(state))
        else:
            print("Run again: ./council.sh run-parallel")

    if state["round"] >= state.get("max_rounds", 12):
        return f"已达最大轮次 {state.get('max_rounds', 12)}"
    return None