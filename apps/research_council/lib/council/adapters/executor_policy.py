"""CouncilExecutorPolicy（委员会执行策略）— Mock/Strict 降级，包装 missionos.executor。"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from council.config import ROOT
from council.mock import generate_mock_output
from missionos.executor.invoke import invoke_command
from missionos.utils import strict_cli_enabled


def mock_mode_enabled() -> bool:
    return os.environ.get("COUNCIL_MOCK", "").strip().lower() in ("1", "true", "yes")


def command_available(command: str) -> bool:
    if not command or not command.strip():
        return False
    parts = shlex.split(command)
    return bool(parts) and shutil.which(parts[0]) is not None


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
) -> tuple[str, bool]:
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