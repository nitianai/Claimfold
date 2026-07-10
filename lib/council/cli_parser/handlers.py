"""Command name → handler registry."""
from council.commands.claims import cmd_claim
from council.commands.daily_cmd import cmd_context, cmd_run_daily
from council.commands.init_cmd import cmd_init
from council.commands.meeting import (
    cmd_ask,
    cmd_audit_summary,
    cmd_continue,
    cmd_next,
    cmd_repair_state,
    cmd_run,
    cmd_run_auto,
    cmd_run_parallel,
    cmd_select,
    cmd_start,
    cmd_status,
    cmd_stop,
    cmd_summary,
    cmd_tui,
    cmd_view,
)
from council.commands.reports import cmd_metrics, cmd_report


def get_handlers():
    return {
        "init": cmd_init,
        "start": cmd_start,
        "run": cmd_run,
        "run-parallel": cmd_run_parallel,
        "run-daily": cmd_run_daily,
        "run-auto": cmd_run_auto,
        "next": cmd_next,
        "summary": cmd_summary,
        "status": cmd_status,
        "continue": cmd_continue,
        "stop": cmd_stop,
        "view": cmd_view,
        "ask": cmd_ask,
        "select": cmd_select,
        "context": cmd_context,
        "metrics": cmd_metrics,
        "report": cmd_report,
        "audit-summary": cmd_audit_summary,
        "repair-state": cmd_repair_state,
        "tui": cmd_tui,
        "claim": cmd_claim,
    }