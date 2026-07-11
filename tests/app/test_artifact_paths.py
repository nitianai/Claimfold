"""artifact_paths_research uses missionos safe_artifact_path."""

from __future__ import annotations

import tempfile
from pathlib import Path

from council.adapters.session_adapter import artifact_paths_research
from missionos.formatting import round_tag


def test_artifact_paths_research_layout():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp)
        paths = artifact_paths_research(meeting_dir, 1, "codex", round_tag)
        tag = "001"
        assert paths["prompt"] == meeting_dir / "prompts" / f"round-{tag}-codex.prompt.md"
        assert paths["raw"] == meeting_dir / "raw" / f"round-{tag}-codex.md"
        assert paths["summary_md"] == meeting_dir / "summaries" / f"round-{tag}-codex.summary.md"
        assert paths["summary_json"] == meeting_dir / "summaries" / f"round-{tag}-codex.summary.json"
        assert paths["error"] == meeting_dir / "errors" / f"round-{tag}-codex.error.md"
        for path in paths.values():
            assert path.is_relative_to(meeting_dir.resolve())