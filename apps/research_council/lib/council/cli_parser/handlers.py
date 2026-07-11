"""Command name → handler registry."""
from council.commands.claims import cmd_claim
from council.commands.daily_context import cmd_context
from council.commands.daily_run import cmd_run_daily
from council.commands.init_cmd import cmd_init
from council.commands.meeting_owner import (
    cmd_ask,
    cmd_continue,
    cmd_status,
    cmd_stop,
    cmd_summary,
    cmd_view,
)
from council.commands.meeting_run import (
    cmd_next,
    cmd_run,
    cmd_run_auto,
    cmd_run_interactive,
    cmd_run_parallel,
    cmd_select,
)
from council.commands.floor_cmd import cmd_floor
from council.commands.session_cmd import cmd_session
from council.commands.meeting_start import cmd_start
from council.commands.meeting_tools import cmd_audit_summary, cmd_repair_state, cmd_tui
from council.commands.web_cmd import cmd_web
from council.commands.reports import cmd_metrics, cmd_report


def get_handlers():
    return {
        "init": cmd_init,
        "start": cmd_start,
        "run": cmd_run,
        "run-parallel": cmd_run_parallel,
        "run-interactive": cmd_run_interactive,
        "session": cmd_session,
        "floor": cmd_floor,
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
        "web": cmd_web,
        "claim": cmd_claim,
    }