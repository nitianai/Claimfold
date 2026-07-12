"""Argparse definitions for council CLI."""
from __future__ import annotations

import argparse

from council.config import DAILY_DEFAULT_GUESTS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="council",
        description="Council Engine V0.1 — deterministic multi-model meeting workflow",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize directories, config, and templates")

    p_start = sub.add_parser("start", help="Start a new meeting")
    p_start.add_argument("topic", help="Meeting topic")
    p_start.add_argument("-q", "--question", help="Owner original question (defaults to topic)")
    p_start.add_argument(
        "-r",
        "--rounds-before-owner",
        type=int,
        default=3,
        help="Guest turns before owner pause (default: 3)",
    )
    p_start.add_argument(
        "--failure-policy",
        choices=["allow_partial", "all_must_succeed", "fail_fast"],
        default="allow_partial",
        help="Guest failure handling: allow_partial | all_must_succeed | fail_fast",
    )
    p_start.add_argument(
        "--require-before-promote",
        action="store_true",
        help="Block claim promote while owner_required (HITL gate)",
    )
    p_start.add_argument(
        "--mode",
        choices=["standard", "investment", "research", "interactive"],
        default="standard",
        help="Meeting mode: standard, investment, research (parallel), or interactive (turn-based)",
    )
    p_start.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Max rounds (default: 12 standard/research, 100 investment)",
    )
    p_start.add_argument(
        "--stale-limit",
        type=int,
        default=5,
        help="Auto-stop after N stale rounds in investment mode (default: 5)",
    )
    p_start.add_argument(
        "--scenario",
        metavar="ID",
        help="Scenario id or slug (e.g. project-development); writes meeting_plan.json",
    )
    p_start.add_argument(
        "--bindings",
        metavar="PATH",
        help="Role→executor bindings YAML (default: config/bindings/<scenario>.yaml)",
    )
    p_start.add_argument(
        "--bind",
        action="append",
        metavar="ROLE=EXECUTOR",
        dest="bind",
        help="Override a role binding (repeatable; CLI wins over --bindings file)",
    )

    p_run = sub.add_parser("run", help="Run next guest turn (prompt → guest → summarizer)")
    p_run.add_argument(
        "--relax",
        action="store_true",
        help="Allow silent mock fallback when CLI fails (default: strict fail-closed)",
    )
    p_run_parallel = sub.add_parser("run-parallel", help="Run parallel round with selected_guests")
    p_run_parallel.add_argument(
        "--relax",
        action="store_true",
        help="Allow silent mock fallback when CLI fails (default: strict fail-closed)",
    )
    p_run_interactive = sub.add_parser(
        "run-interactive",
        help="Run turn-based interactive round (sequential, guests see prior turns)",
    )
    p_run_interactive.add_argument(
        "--relax",
        action="store_true",
        help="Allow silent mock fallback when CLI fails (default: strict fail-closed)",
    )

    p_session = sub.add_parser("session", help="Interactive session — inspect / step / resume")
    session_sub = p_session.add_subparsers(dest="session_cmd", required=True)
    p_session_inspect = session_sub.add_parser("inspect", help="Show interactive session state (JSON)")
    p_session_inspect.add_argument(
        "--annotations",
        action="store_true",
        help="Include AGREE/DISAGREE/QUESTION annotation projection",
    )
    session_sub.add_parser("step", help="Advance one floor turn")
    session_sub.add_parser("resume", help="Resume paused session until round completes")
    p_session_replay = session_sub.add_parser("replay", help="Replay session events from context_cursor")
    p_session_replay.add_argument("--tail", type=int, default=20, help="Events before cursor to show")

    p_floor = sub.add_parser("floor", help="Floor protocol — request / yield / interrupt")
    floor_sub = p_floor.add_subparsers(dest="floor_cmd", required=True)
    p_floor_req = floor_sub.add_parser("request", help="Guest requests speaking floor")
    p_floor_req.add_argument("guest", help="Guest id")
    p_floor_req.add_argument("--urgency", type=int, default=0, help="Higher = earlier in queue")
    p_floor_req.add_argument("--build-on", dest="build_on", default="", help="Message id to build on")
    p_floor_req.add_argument(
        "--type",
        default="SPEAK",
        choices=["SPEAK", "CHALLENGE", "CLARIFY"],
        help="Request type",
    )
    p_floor_yield = floor_sub.add_parser("yield", help="Current speaker yields floor")
    p_floor_yield.add_argument("guest", help="Guest id")
    p_floor_int = floor_sub.add_parser("interrupt", help="Request interrupt")
    p_floor_int.add_argument("guest", help="Requesting guest")
    p_floor_int.add_argument("target", help="Target guest")
    p_floor_int.add_argument("--message", default="", help="Target message id")
    p_daily = sub.add_parser(
        "run-daily",
        help="14:30 daily: prior final + script context → parallel guests → daily_decision.md",
    )
    p_daily.add_argument("scope", help="Market scope e.g. TSLA、VIX、美债")
    p_daily.add_argument(
        "--guests",
        default=",".join(DAILY_DEFAULT_GUESTS),
        help="Comma-separated guest aliases (default: grok,codex,qoder)",
    )
    p_daily.add_argument(
        "--prior-meeting",
        default="",
        help="Prior meeting id for after-hours report (default: latest final.md)",
    )
    p_daily.add_argument(
        "--skip-context-llm",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip context_collector LLM; script + prior final only (default: true)",
    )
    p_daily.add_argument(
        "--force-owner-continue",
        action="store_true",
        help="Clear owner_required for unattended 14:30 daily run (writes audit note)",
    )
    p_daily.add_argument(
        "--relax",
        action="store_true",
        help="Allow silent mock fallback when CLI fails (default: strict fail-closed)",
    )
    sub.add_parser("run-auto", help="Auto-run investment committee until stop condition")
    sub.add_parser("metrics", help="Compute and save meeting metrics")
    sub.add_parser("report", help="Generate investment_report.md + council_experiment_report.md")

    p_select = sub.add_parser("select", help="Set guests for next parallel round")
    p_select.add_argument("guests", nargs="+", help="Guest ids or aliases (claude, grok, ...)")

    p_context = sub.add_parser("context", help="Generate shared market_context")
    p_context.add_argument("scope", help="Market scope / focus for context collection")
    sub.add_parser("next", help="Preview next prompt without invoking models")
    sub.add_parser("summary", help="Show meeting summary")
    sub.add_parser("status", help="Show meeting_state.json")
    sub.add_parser("continue", help="Release owner_required, allow 3 more turns")
    sub.add_parser("stop", help="Stop meeting and write final.md")

    p_view = sub.add_parser("view", help="Record an owner view")
    p_view.add_argument("text", help="Owner viewpoint text")

    p_ask = sub.add_parser("ask", help="Update next question")
    p_ask.add_argument("text", help="New question")

    p_audit = sub.add_parser("audit-summary", help="Audit prompt/raw/summary for a round")
    p_audit.add_argument("round", help="Round number (e.g. 1 or 001)")
    p_audit.add_argument("guest", help="Guest name (e.g. qwen)")

    sub.add_parser("repair-state", help="Migrate legacy guest names and rebuild state from summaries")
    sub.add_parser("repair-slots", help="Rebuild guest_slots projection from events or artifacts")
    sub.add_parser("tui", help="Optional tmux-based TUI")

    p_web = sub.add_parser("web", help="Start chat-room web UI (default http://127.0.0.1:8787)")
    p_web.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p_web.add_argument("--port", type=int, default=8787, help="Bind port (default: 8787)")

    p_claim = sub.add_parser("claim", help="Claim Lifecycle V0.2 — ledger + index")
    claim_sub = p_claim.add_subparsers(dest="claim_cmd", required=True)

    p_promote = claim_sub.add_parser("promote", help="Owner promote state item to TENTATIVE claim")
    p_promote.add_argument(
        "--from-state",
        required=True,
        help="State ref e.g. conflicts[0] or confirmed_points[2]",
    )
    p_promote.add_argument("--meeting", help="Source meeting id (default: current)")
    p_promote.add_argument("--domain", required=True, help="scope.domain e.g. finance")
    p_promote.add_argument("--subjects", required=True, help="Comma-separated scope.subjects")
    p_promote.add_argument("--regime-tags", default="", help="Comma-separated regime_tags")
    p_promote.add_argument("--valid-from", default="", help="scope.valid_from YYYY-MM-DD")
    p_promote.add_argument("--valid-until", default="", help="scope.valid_until YYYY-MM-DD")
    p_promote.add_argument("--conditions", default="", help="Semicolon-separated scope.conditions")
    p_promote.add_argument(
        "--evidence",
        action="append",
        required=True,
        help="Evidence path relative to meeting (repeatable)",
    )
    p_promote.add_argument(
        "--owner-override",
        action="store_true",
        help="Bypass non-promotion validator with audit note",
    )

    p_retire = claim_sub.add_parser("retire", help="Owner retire a claim")
    p_retire.add_argument("claim_id", help="e.g. clm-000001")
    p_retire.add_argument("--reason", default="owner decision")

    claim_sub.add_parser("rebuild-index", help="Rebuild claims_index.json from ledger")
    claim_sub.add_parser("list", help="List claims from index")
    claim_sub.add_parser("verify", help="Verify three-meeting claim lifecycle chain")

    return parser