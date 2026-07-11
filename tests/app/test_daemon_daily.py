"""Daemon daily trigger tests."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def test_daemon_daily_skips_without_session():
    root = _repo_root()
    script = root / "scripts" / "council-daemon.sh"
    with tempfile.TemporaryDirectory() as tmp:
        data_root = Path(tmp)
        env = {
            **dict(__import__("os").environ),
            "COUNCIL_DATA_ROOT": str(data_root),
            "PYTHONPATH": f"{root}/platform:{root}/apps/research_council/lib",
        }
        result = subprocess.run(
            [str(script), "daily", "TSLA"],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=env,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["skipped"] is True


def test_systemd_examples_exist():
    root = _repo_root()
    for name in (
        "council-daemon.service.example",
        "council-daily.service.example",
        "council-daily.timer.example",
    ):
        assert (root / "scripts" / "systemd" / name).is_file()