"""v1 post-evolution mock validation — gates must not break research loop."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO / "scripts" / "run_v1_validation_experiment.sh"


def test_v1_validation_experiment_script_passes():
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **dict(__import__("os").environ),
            "COUNCIL_DATA_ROOT": tmp,
        }
        proc = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        report = json.loads(proc.stdout.strip())
        assert report["verdict"] == "PASS"
        assert report["semantic_loop_ok"] is True
        assert report["rounds"] >= 2
        assert report["confirmed_points"] > 0
        assert report["guest_slots"] > 0
        assert report["guest_failure_rate_pct"] == 0