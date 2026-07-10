"""Subprocess invocation for guest / summarizer CLIs."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from council.config import ROOT, SCRIPTS_DIR
from council.mock import generate_mock_output
from utils import strict_cli_enabled


def invoke_script(command: str, *, timeout_seconds: int = 60) -> tuple[str, bool]:
    """Run a script guest command (no stdin). Returns (stdout, success)."""
    if not command or not command.strip():
        return "", False
    if mock_mode_enabled():
        return "", False
    parts = shlex.split(command)
    if not parts or not shutil.which(parts[0]):
        return "", False
    try:
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(ROOT),
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "script failed").strip()
            return f"# Script Error\n\n{err}\n", False
        return (result.stdout or "").strip() + "\n", True
    except subprocess.TimeoutExpired:
        return "# Script Error\n\nTimeout\n", False
    except Exception as exc:
        return f"# Script Error\n\n{exc}\n", False


def fetch_equity_context_block(symbol: str, meeting_dir: Path) -> tuple[str, dict[str, Any]]:
    script = SCRIPTS_DIR / "fetch_equity.py"
    if not script.is_file():
        raise SystemExit(
            f"Required script missing: fetch_equity.py\n"
            f"  expected: {script}\n"
            f"  ROOT: {ROOT}"
        )
    out_path = meeting_dir / "context" / f"{symbol.lower()}_data.md"
    json_path = meeting_dir / "context" / f"{symbol.lower()}_data.json"
    cmd = f"python3 {script} {symbol} --out {out_path} --json {json_path}"
    body, ok = invoke_script(cmd, timeout_seconds=30)
    if ok and out_path.exists():
        body = out_path.read_text(encoding="utf-8").strip()
    meta: dict[str, Any] = {"symbol": symbol.upper(), "ok": ok}
    if json_path.exists():
        try:
            meta.update(json.loads(json_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return body, meta


def command_available(command: str) -> bool:
    if not command or not command.strip():
        return False
    parts = shlex.split(command)
    if not parts:
        return False
    return shutil.which(parts[0]) is not None


def mock_mode_enabled() -> bool:
    return os.environ.get("COUNCIL_MOCK", "").strip().lower() in ("1", "true", "yes")


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
    """Run guest/summarizer CLI. Returns (output, used_mock)."""
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

    parts = shlex.split(command)
    try:
        result = subprocess.run(
            parts,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            return _fail_or_mock_cli(
                kind=kind,
                guest=guest,
                round_num=round_num,
                label=f"{mock_label} (CLI failed: {stderr[:200]})",
                reason=stderr[:200] or f"exit {result.returncode}",
            )
        output = (result.stdout or "").strip()
        if not output:
            return _fail_or_mock_cli(
                kind=kind,
                guest=guest,
                round_num=round_num,
                label=mock_label,
                reason="empty stdout",
            )
        return output, False
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _fail_or_mock_cli(
            kind=kind,
            guest=guest,
            round_num=round_num,
            label=f"{mock_label} (error: {exc})",
            reason=str(exc),
        )
