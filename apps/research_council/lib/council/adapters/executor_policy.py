"""CouncilExecutorPolicy（委员会执行策略）— inspect_invoke + Mock/Strict，包装 missionos.executor。"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from council.config import ROOT
from council.mock import generate_mock_output
from missionos.executor.invoke import invoke_command
from missionos.utils import strict_cli_enabled

InvokeDecision = Literal["allow", "deny", "require_owner"]


class ExecutorDeniedError(Exception):
    """Strict 策略拒绝执行；runner 应标记 Guest Failed 并保留审计链。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class InvokeContext:
    command: str
    guest: str
    round_num: int
    kind: str
    guest_cfg: dict[str, Any] | None = None


def mock_mode_enabled() -> bool:
    return os.environ.get("COUNCIL_MOCK", "").strip().lower() in ("1", "true", "yes")


def command_available(command: str) -> bool:
    if not command or not command.strip():
        return False
    parts = shlex.split(command)
    return bool(parts) and shutil.which(parts[0]) is not None


def inspect_invoke(ctx: InvokeContext) -> InvokeDecision:
    """执行前策略门：mock 允许；strict 缺命令/不可用时 deny；relax 允许后续 mock 降级。"""
    if mock_mode_enabled():
        return "allow"
    if ctx.guest_cfg and ctx.guest_cfg.get("enabled") is False:
        return "deny"
    if ctx.guest_cfg and str(ctx.guest_cfg.get("invoke_policy") or "").strip() == "require_owner":
        if not command_available(ctx.command):
            return "require_owner"
    cmd = (ctx.command or "").strip()
    if not cmd or not command_available(cmd):
        return "deny" if strict_cli_enabled() else "allow"
    return "allow"


def _deny_reason(ctx: InvokeContext) -> str:
    if ctx.guest_cfg and ctx.guest_cfg.get("enabled") is False:
        return f"guest disabled: {ctx.guest}"
    cmd = (ctx.command or "").strip()
    if not cmd:
        return "empty command"
    if not command_available(cmd):
        return f"command unavailable: {cmd[:120]}"
    return "invoke denied by policy"


def record_executor_denied(
    meeting_dir: Path,
    event_log: Any | None,
    *,
    round_num: int,
    guest: str,
    kind: str,
    reason: str,
    command: str = "",
) -> None:
    from council.adapters.meeting_events import publish_executor_denied
    from council.adapters.session_adapter import artifact_paths_research
    from council.formatting import round_tag
    from council.meeting_helpers import write_error_file

    paths = artifact_paths_research(meeting_dir, round_num, guest, round_tag)
    if not paths["error"].exists():
        write_error_file(
            paths["error"],
            guest=guest,
            round_num=round_num,
            error=f"ExecutorDenied: {reason}",
        )
    if event_log is not None:
        publish_executor_denied(
            event_log,
            round_num=round_num,
            guest=guest,
            kind=kind,
            reason=reason,
            command=command,
        )


def _fail_or_mock_cli(
    *,
    kind: str,
    guest: str,
    round_num: int,
    label: str,
    reason: str,
) -> tuple[str, bool]:
    if strict_cli_enabled():
        raise SystemExit(f"STRICT: {guest} CLI failed — {reason}")
    print(f"⚠ WARNING: {guest} ({kind}) returned mock data — {reason}", file=sys.stderr)
    return generate_mock_output(kind=kind, guest=guest, round_num=round_num, label=label), True


def _handle_policy_deny(
    ctx: InvokeContext,
    *,
    meeting_dir: Path | None,
    event_log: Any | None,
) -> None:
    reason = _deny_reason(ctx)
    if meeting_dir is not None:
        record_executor_denied(
            meeting_dir,
            event_log,
            round_num=ctx.round_num,
            guest=ctx.guest,
            kind=ctx.kind,
            reason=reason,
            command=ctx.command,
        )
        raise ExecutorDeniedError(reason)
    raise SystemExit(f"STRICT: {ctx.guest} CLI denied — {reason}")


def invoke_script(command: str, *, cwd: str | Path | None = None, timeout_seconds: int = 60) -> tuple[str, bool]:
    if not command or not command.strip():
        return "", False
    if mock_mode_enabled():
        return "", False
    if not command_available(command):
        return "", False
    result = invoke_command(command, cwd=str(cwd) if cwd else None, timeout_seconds=timeout_seconds)
    if result.timed_out:
        return "# Script Error\n\nTimeout\n", False
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "script failed").strip()
        return f"# Script Error\n\n{err}\n", False
    return (result.stdout or "").strip() + "\n", True


def invoke_cli(
    command: str,
    prompt: str,
    *,
    mock_label: str,
    round_num: int,
    guest: str,
    kind: str,
    timeout_seconds: int = 600,
    meeting_dir: Path | None = None,
    event_log: Any | None = None,
    guest_cfg: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    ctx = InvokeContext(
        command=command,
        guest=guest,
        round_num=round_num,
        kind=kind,
        guest_cfg=guest_cfg,
    )
    decision = inspect_invoke(ctx)
    if decision == "deny":
        _handle_policy_deny(ctx, meeting_dir=meeting_dir, event_log=event_log)
    if decision == "require_owner":
        reason = _deny_reason(ctx)
        if meeting_dir is not None:
            record_executor_denied(
                meeting_dir,
                event_log,
                round_num=round_num,
                guest=guest,
                kind=kind,
                reason=f"require_owner: {reason}",
                command=command,
            )
            raise ExecutorDeniedError(f"require_owner: {reason}")
        raise SystemExit(f"STRICT: {guest} requires owner approval — {reason}")

    if mock_mode_enabled():
        return (
            generate_mock_output(kind=kind, guest=guest, round_num=round_num, label="forced-mock"),
            True,
        )
    if not command_available(command):
        return _fail_or_mock_cli(
            kind=kind,
            guest=guest,
            round_num=round_num,
            label=mock_label,
            reason=f"command unavailable: {command[:80]}",
        )

    result = invoke_command(command, stdin=prompt, cwd=str(ROOT), timeout_seconds=timeout_seconds)
    if result.timed_out:
        return _fail_or_mock_cli(
            kind=kind,
            guest=guest,
            round_num=round_num,
            label=f"{mock_label} (error: timeout)",
            reason="timeout",
        )
    if result.returncode != 0:
        return _fail_or_mock_cli(
            kind=kind,
            guest=guest,
            round_num=round_num,
            label=f"{mock_label} (CLI failed: {result.stderr[:200]})",
            reason=result.stderr[:200] or f"exit {result.returncode}",
        )
    output = result.stdout
    if not output:
        return _fail_or_mock_cli(
            kind=kind,
            guest=guest,
            round_num=round_num,
            label=mock_label,
            reason="empty stdout",
        )
    return output, False