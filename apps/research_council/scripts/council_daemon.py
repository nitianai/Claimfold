#!/usr/bin/env python3
"""Council session daemon — health check and state watch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from council.config import DATA_ROOT, REPO_ROOT
from missionos.daemon import check_session_health, run_watch
from missionos.session import SessionStore
from missionos.utils import validate_meeting_id


def _store() -> SessionStore:
    return SessionStore(root=DATA_ROOT)


def cmd_check(_: argparse.Namespace) -> int:
    health = check_session_health(_store(), validate_fn=validate_meeting_id)
    payload = {
        "ok": health.ok,
        "meeting_id": health.meeting_id,
        "meeting_dir": str(health.meeting_dir) if health.meeting_dir else None,
        "state_mtime": health.state_mtime,
        "issues": list(health.issues),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if health.ok else 1


def cmd_watch(args: argparse.Namespace) -> int:
    return run_watch(
        _store(),
        interval_seconds=args.interval,
        validate_fn=validate_meeting_id,
        max_ticks=args.max_ticks,
    )


def cmd_daily(args: argparse.Namespace) -> int:
    """Run ./council.sh run-daily when an active healthy session exists."""
    health = check_session_health(_store(), validate_fn=validate_meeting_id)
    if not health.ok:
        print(
            json.dumps(
                {"skipped": True, "reason": "no healthy session", "issues": list(health.issues)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    scope = (args.scope or os.environ.get("COUNCIL_DAILY_SCOPE", "")).strip()
    if not scope:
        print(json.dumps({"error": "scope required (arg or COUNCIL_DAILY_SCOPE)"}, indent=2), file=sys.stderr)
        return 2

    council_sh = REPO_ROOT / "council.sh"
    cmd = [str(council_sh), "run-daily", scope]
    if not args.with_context_llm:
        cmd.append("--skip-context-llm")

    env = {**os.environ, "COUNCIL_DATA_ROOT": str(DATA_ROOT)}
    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode != 0:
        print(json.dumps({"error": "run-daily failed", "code": result.returncode}, indent=2), file=sys.stderr)
    return int(result.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Council session daemon")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="One-shot session health check (JSON to stdout)")
    p_check.set_defaults(func=cmd_check)

    p_watch = sub.add_parser("watch", help="Poll session pointer and meeting_state changes")
    p_watch.add_argument("--interval", type=int, default=30, help="Poll interval seconds")
    p_watch.add_argument("--max-ticks", type=int, default=None, help="Stop after N polls (tests)")
    p_watch.set_defaults(func=cmd_watch)

    p_daily = sub.add_parser("daily", help="Run council.sh run-daily for active session (cron/systemd)")
    p_daily.add_argument("scope", nargs="?", default="", help="Daily scope (or COUNCIL_DAILY_SCOPE)")
    p_daily.add_argument("--with-context-llm", action="store_true", help="Allow context LLM in run-daily")
    p_daily.set_defaults(func=cmd_daily)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())