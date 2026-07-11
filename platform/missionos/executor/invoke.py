"""Pure subprocess command invocation."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class InvokeResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def invoke_command(
    command: str | Sequence[str],
    *,
    stdin: str = "",
    cwd: str | None = None,
    timeout_seconds: int = 600,
) -> InvokeResult:
    """Run a subprocess command and return structured output."""
    if isinstance(command, str):
        parts = shlex.split(command)
    else:
        parts = list(command)
    try:
        result = subprocess.run(
            parts,
            input=stdin or None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=cwd,
        )
        return InvokeResult(
            returncode=result.returncode,
            stdout=(result.stdout or "").strip(),
            stderr=(result.stderr or "").strip(),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
        return InvokeResult(returncode=-1, stdout=stdout, stderr=stderr, timed_out=True)
    except OSError as exc:
        return InvokeResult(returncode=-1, stdout="", stderr=str(exc))