"""Integration tests for project-root path resolution (P0 path SoT)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from council.config import (
    CLAIMS_DIR,
    CONFIG_FILE,
    CURRENT_MEETING_FILE,
    GUEST_RESEARCH_TEMPLATE,
    MEETINGS_DIR,
    ROOT,
    SCRIPTS_DIR,
)
from council.guests import load_guests
from council.prompts import generate_research_prompt


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_root_points_to_project_not_lib():
    assert ROOT == _project_root()
    assert ROOT.name != "lib"
    assert (ROOT / "lib" / "council" / "config.py").is_file()


def test_derived_paths_under_project_root():
    assert MEETINGS_DIR == ROOT / "meetings"
    assert CLAIMS_DIR == ROOT / "claims"
    assert CONFIG_FILE == ROOT / "config" / "guests.yaml"
    assert CURRENT_MEETING_FILE == ROOT / ".current_meeting"
    assert SCRIPTS_DIR == ROOT / "scripts"
    assert GUEST_RESEARCH_TEMPLATE == ROOT / "prompts" / "guest" / "research.md"
    assert not str(MEETINGS_DIR).startswith(str(ROOT / "lib" / "meetings"))
    assert not str(CLAIMS_DIR).startswith(str(ROOT / "lib" / "claims"))


def test_guest_config_loads_from_project_root():
    guests = load_guests()
    assert guests, "config/guests.yaml must define at least one guest"


def test_research_prompt_template_exists():
    assert GUEST_RESEARCH_TEMPLATE.is_file(), f"missing: {GUEST_RESEARCH_TEMPLATE}"


def test_fetch_equity_script_resolvable():
    script = SCRIPTS_DIR / "fetch_equity.py"
    assert script.is_file(), f"missing: {script}"


def test_current_meeting_pointer_when_present():
    if not CURRENT_MEETING_FILE.is_file():
        return
    meeting_id = CURRENT_MEETING_FILE.read_text(encoding="utf-8").strip()
    assert meeting_id.startswith("meet-")
    assert (MEETINGS_DIR / meeting_id).is_dir()


def test_claims_index_when_present():
    index_path = CLAIMS_DIR / "claims_index.json"
    if not index_path.is_file():
        return
    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert "claims" in data


def test_init_does_not_create_lib_shadow_dirs(tmp_path: Path | None = None):
    """init must write runtime dirs under project ROOT, not lib/."""
    with tempfile.TemporaryDirectory() as tmp:
        fake_root = Path(tmp)
        (fake_root / "lib" / "council").mkdir(parents=True)
        # Simulate corrected layout: only code under lib/, runtime at root.
        for name in ("meetings", "claims", "config", "prompts", "scripts"):
            (fake_root / name).mkdir()
        (fake_root / "config" / "guests.yaml").write_text("guests:\n  a: {enabled: true}\n", encoding="utf-8")
        (fake_root / "prompts" / "guest").mkdir(parents=True, exist_ok=True)
        (fake_root / "prompts" / "guest" / "research.md").write_text("{{topic}}\n", encoding="utf-8")

        lib_shadows = [
            fake_root / "lib" / "meetings",
            fake_root / "lib" / "claims",
            fake_root / "lib" / "config",
            fake_root / "lib" / "prompts",
        ]
        for p in lib_shadows:
            assert not p.exists(), f"fixture should not pre-create shadow: {p}"

        # Runtime data belongs at project root in the fixture.
        assert (fake_root / "meetings").is_dir()
        assert (fake_root / "claims").is_dir()
        assert not (fake_root / "lib" / "meetings").exists()


def test_research_prompt_uses_research_template_not_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260710-999999"
        for sub in ("context", "prompts", "raw", "summaries"):
            (meeting_dir / sub).mkdir(parents=True)
        (meeting_dir / "context" / "market_context.md").write_text("ctx", encoding="utf-8")
        state = {
            "meeting_id": meeting_dir.name,
            "topic": "TSLA",
            "output_format": "research",
            "round_mode": "parallel",
            "owner_question": "q",
            "confirmed_points": [],
            "conflicts": [],
            "open_questions": [],
            "guest_summaries": {},
            "owner_views": [],
            "next_question": "focus",
        }
        guests = {"codex": {"role": "logic", "enabled": True}}
        body = generate_research_prompt(state, guests, "codex", meeting_dir)
        assert "结构化研究会议" in body, "must use prompts/guest/research.md, not template.md fallback"
        assert "历史试探性主张" in body
        assert "ctx" in body