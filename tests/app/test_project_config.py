"""Project config API tests."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest import mock

import yaml

from council.web.service import CouncilWebService


def test_save_project_config_updates_guests_yaml():
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp) / "config"
        config_dir.mkdir()
        src = Path(__file__).resolve().parents[2] / "apps/research_council/config/guests.yaml"
        config_file = config_dir / "guests.yaml"
        shutil.copy(src, config_file)

        svc = CouncilWebService()
        with mock.patch("council.web.service.CONFIG_FILE", config_file):
            payload = svc.project_config_payload()
            rows = payload["guest_rows"]
            codex = next(r for r in rows if r["id"] == "codex")
            codex["role"] = "Test Role Updated"
            codex["enabled"] = True

            result = svc.save_project_config(rows)
            assert result["ok"] is True

            with config_file.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert data["guests"]["codex"]["role"] == "Test Role Updated"