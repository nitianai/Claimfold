"""Daemon watch loop for session state changes."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from missionos.daemon.health import SessionHealth, check_session_health
from missionos.protocols import SessionStoreProtocol


def run_watch(
    store: SessionStoreProtocol,
    *,
    interval_seconds: int = 30,
    validate_fn: Callable[[str], str] | None = None,
    max_ticks: int | None = None,
    out=print,
) -> int:
    """Poll session health; emit when meeting_state mtime changes. Returns exit code."""
    interval = max(1, int(interval_seconds))
    last_mtime: float | None = None
    ticks = 0

    while True:
        health = check_session_health(store, validate_fn=validate_fn)
        code = _emit_health(health, last_mtime=last_mtime, out=out)
        if code != 0:
            return code

        if health.state_mtime is not None and health.state_mtime != last_mtime:
            if last_mtime is not None:
                out(f"state changed: {health.meeting_id}")
            last_mtime = health.state_mtime

        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            return 0
        time.sleep(interval)


def _emit_health(health: SessionHealth, *, last_mtime: float | None, out=print) -> int:
    if health.ok:
        if last_mtime is None:
            out(f"session ok: {health.meeting_id} ({health.meeting_dir})")
        return 0
    for issue in health.issues:
        print(issue, file=sys.stderr)
    return 1