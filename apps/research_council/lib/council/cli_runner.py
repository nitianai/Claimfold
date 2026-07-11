"""Subprocess invocation for guest / summarizer CLIs — 薄封装，策略在 executor_policy。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from council.adapters.executor_policy import (
    command_available,
    invoke_cli,
    invoke_script,
    mock_mode_enabled,
)
from council.config import ROOT, SCRIPTS_DIR

__all__ = [
    "command_available",
    "fetch_equity_context_block",
    "fetch_macro_context_block",
    "invoke_cli",
    "invoke_script",
    "mock_mode_enabled",
]


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
    body, ok = invoke_script(cmd, cwd=ROOT, timeout_seconds=30)
    if ok and out_path.exists():
        body = out_path.read_text(encoding="utf-8").strip()
    meta: dict[str, Any] = {"symbol": symbol.upper(), "ok": ok}
    if json_path.exists():
        try:
            meta.update(json.loads(json_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return body, meta


def fetch_macro_context_block(
    symbol: str,
    meeting_dir: Path,
    *,
    label: str = "",
    slug: str = "",
) -> tuple[str, dict[str, Any]]:
    script = SCRIPTS_DIR / "fetch_macro.py"
    if not script.is_file():
        raise SystemExit(f"Required script missing: fetch_macro.py\n  expected: {script}")
    file_slug = slug or symbol.replace("^", "").replace("=", "").replace("-", "_").lower()
    out_path = meeting_dir / "context" / f"macro_{file_slug}_data.md"
    json_path = meeting_dir / "context" / f"macro_{file_slug}_data.json"
    label_arg = f' --label "{label}"' if label else ""
    cmd = f'python3 {script} "{symbol}"{label_arg} --out {out_path} --json {json_path}'
    body, ok = invoke_script(cmd, cwd=ROOT, timeout_seconds=30)
    if ok and out_path.exists():
        body = out_path.read_text(encoding="utf-8").strip()
    meta: dict[str, Any] = {"symbol": symbol, "label": label, "ok": ok}
    if json_path.exists():
        try:
            meta.update(json.loads(json_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return body, meta