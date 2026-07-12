"""Meeting experiment archive script tests."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO / "scripts" / "archive_meeting_experiment.sh"
ARCHIVE_PY = REPO / "apps" / "research_council" / "scripts" / "archive_meeting_experiment.py"


def _seed_meeting(root: Path, meeting_id: str) -> Path:
    meeting_dir = root / "meetings" / meeting_id
    for sub in ("raw", "summaries", "prompts", "context"):
        (meeting_dir / sub).mkdir(parents=True, exist_ok=True)
    state = {
        "meeting_id": meeting_id,
        "topic": "归档测试",
        "meeting_mode": "research",
        "round": 1,
        "status": "running",
        "confirmed_points": ["CP-A"],
        "conflicts": ["CF-A"],
        "open_questions": ["OQ-A"],
        "history": [
            {
                "mode": "parallel",
                "entries": [
                    {
                        "guest": "nemo",
                        "success": True,
                        "duration_s": 12.0,
                        "used_mock_guest": False,
                        "raw_output_path": "raw/round-001-nemo.md",
                        "confirmed_points_added": 1,
                        "conflicts_added": 1,
                        "open_questions_added": 1,
                    }
                ],
            }
        ],
        "guest_slots": {"r001:nemo": {"phase": "Succeeded"}},
    }
    (meeting_dir / "meeting_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (meeting_dir / "raw" / "round-001-nemo.md").write_text("nemo raw\n", encoding="utf-8")
    (meeting_dir / "summaries" / "round-001-nemo.summary.json").write_text(
        json.dumps(
            {
                "confirmed_points": ["CP-A"],
                "conflicts": ["CF-A"],
                "open_questions": ["OQ-A"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / ".current_meeting").write_text(meeting_id + "\n", encoding="utf-8")
    return meeting_dir


def test_archive_meeting_experiment_script():
    assert SCRIPT.is_file()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meeting_id = "meet-20260712-999999"
        meeting_dir = _seed_meeting(root, meeting_id)
        baseline_id = "meet-20260710-000001"
        _seed_meeting(root, baseline_id)

        proc = subprocess.run(
            ["bash", str(SCRIPT), meeting_id, "--baseline", baseline_id],
            cwd=REPO,
            env={**dict(__import__("os").environ), "COUNCIL_DATA_ROOT": str(root)},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

        archive_path = meeting_dir / "experiment_archive.json"
        assert archive_path.is_file()
        report = json.loads(archive_path.read_text(encoding="utf-8"))
        assert report["verdict"] == "ARCHIVED"
        assert report["meeting_id"] == meeting_id
        assert report["metrics"]["meeting_id"] == meeting_id
        assert (meeting_dir / "metrics.json").is_file()
        assert (meeting_dir / "metrics.md").is_file()
        assert (meeting_dir / "quality_comparison.md").is_file()
        assert report["baseline"]["meeting_id"] == baseline_id