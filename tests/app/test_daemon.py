"""Session daemon health and watch tests."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from missionos.daemon import check_session_health, run_watch
from missionos.session import SessionStore
from missionos.utils import validate_meeting_id


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def test_check_session_health_no_pointer():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(root=Path(tmp))
        health = check_session_health(store, validate_fn=validate_meeting_id)
        assert not health.ok
        assert health.issues == ("no active session pointer",)


def test_check_session_health_ok():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = SessionStore(root=root)
        meeting_id = "meet-20260711-120000"
        meeting_dir = store.resolve_session_dir(meeting_id, validate_fn=validate_meeting_id)
        meeting_dir.mkdir(parents=True)
        store.write_pointer(meeting_id)
        store.save_state(meeting_dir, {"topic": "daemon", "round": 1})

        health = check_session_health(store, validate_fn=validate_meeting_id)
        assert health.ok
        assert health.meeting_id == meeting_id
        assert health.meeting_dir == meeting_dir
        assert health.state_mtime is not None


def test_check_session_health_invalid_pointer():
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(root=Path(tmp))
        store.write_pointer("bad-id")
        health = check_session_health(store, validate_fn=validate_meeting_id)
        assert not health.ok
        assert health.meeting_id == "bad-id"


def test_run_watch_max_ticks():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = SessionStore(root=root)
        meeting_id = "meet-20260711-120000"
        meeting_dir = store.resolve_session_dir(meeting_id, validate_fn=validate_meeting_id)
        meeting_dir.mkdir(parents=True)
        store.write_pointer(meeting_id)
        store.save_state(meeting_dir, {"topic": "watch"})

        assert run_watch(store, interval_seconds=1, validate_fn=validate_meeting_id, max_ticks=1) == 0


def test_council_daemon_cli_check():
    root = _repo_root()
    script = root / "scripts" / "council-daemon.sh"
    with tempfile.TemporaryDirectory() as tmp:
        data_root = Path(tmp)
        meeting_id = "meet-20260711-130000"
        meetings = data_root / "meetings" / meeting_id
        meetings.mkdir(parents=True)
        (meetings / "meeting_state.json").write_text(
            json.dumps({"topic": "cli", "round": 0}) + "\n",
            encoding="utf-8",
        )
        (data_root / ".current_meeting").write_text(meeting_id + "\n", encoding="utf-8")

        env = {"COUNCIL_DATA_ROOT": str(data_root), "PATH": "/usr/bin:/bin"}
        result = subprocess.run(
            [str(script), "check"],
            capture_output=True,
            text=True,
            cwd=str(root),
            env={
                **dict(__import__("os").environ),
                **env,
                "PYTHONPATH": f"{root}/platform:{root}/apps/research_council/lib",
            },
        )
        assert result.returncode == 0, result.stderr or result.stdout
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["meeting_id"] == meeting_id