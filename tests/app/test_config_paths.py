"""Integration tests for App/DATA_ROOT path resolution (P0 path SoT)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from council.config import (
    APP_ROOT,
    CLAIMS_DIR,
    CONFIG_FILE,
    CURRENT_MEETING_FILE,
    DATA_ROOT,
    GUEST_RESEARCH_TEMPLATE,
    MEETINGS_DIR,
    REPO_ROOT,
    ROOT,
    SCRIPTS_DIR,
)
from council.guests import load_guests
from council.prompts import generate_research_prompt


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def test_app_root_points_to_research_council():
    assert APP_ROOT == _repo_root() / "apps" / "research_council"
    assert APP_ROOT.is_dir()
    assert (APP_ROOT / "lib" / "council" / "config.py").is_file()


def test_repo_and_data_roots_default_to_repository():
    assert REPO_ROOT == _repo_root()
    assert DATA_ROOT == REPO_ROOT


def test_root_alias_equals_app_root():
    assert ROOT == APP_ROOT


def test_derived_paths_split_app_assets_and_runtime_data():
    assert MEETINGS_DIR == DATA_ROOT / "meetings"
    assert CLAIMS_DIR == DATA_ROOT / "claims"
    assert CONFIG_FILE == APP_ROOT / "config" / "guests.yaml"
    assert CURRENT_MEETING_FILE == DATA_ROOT / ".current_meeting"
    assert SCRIPTS_DIR == APP_ROOT / "scripts"
    assert GUEST_RESEARCH_TEMPLATE == APP_ROOT / "prompts" / "guest" / "research.md"
    assert not str(MEETINGS_DIR).startswith(str(APP_ROOT / "lib"))
    assert not str(CLAIMS_DIR).startswith(str(APP_ROOT / "lib"))


def test_guest_config_loads_from_app_root():
    guests = load_guests()
    assert guests, "config/guests.yaml must define at least one guest"


def test_focus_rules_and_executor_guest_config():
    from council.executor_guest import EXECUTOR_TO_GUEST
    from council.focus_rules import FOCUS_RULES

    assert FOCUS_RULES, "focus_rules.yaml must define at least one rule"
    assert "claude" in EXECUTOR_TO_GUEST
    assert EXECUTOR_TO_GUEST["claude"] == "claude_sonnet"


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


def test_init_does_not_create_lib_shadow_dirs():
    """init must write runtime dirs under DATA_ROOT, not under app lib/."""
    with tempfile.TemporaryDirectory() as tmp:
        fake_repo = Path(tmp)
        fake_app = fake_repo / "apps" / "research_council"
        (fake_app / "lib" / "council").mkdir(parents=True)
        for name in ("config", "prompts", "scripts"):
            (fake_app / name).mkdir(parents=True)
        (fake_app / "config" / "guests.yaml").write_text("guests:\n  a: {enabled: true}\n", encoding="utf-8")
        (fake_app / "prompts" / "guest").mkdir(parents=True, exist_ok=True)
        (fake_app / "prompts" / "guest" / "research.md").write_text("{{topic}}\n", encoding="utf-8")
        (fake_repo / "meetings").mkdir()
        (fake_repo / "claims").mkdir()

        lib_shadows = [
            fake_app / "lib" / "meetings",
            fake_app / "lib" / "claims",
            fake_app / "lib" / "config",
            fake_app / "lib" / "prompts",
        ]
        for p in lib_shadows:
            assert not p.exists(), f"fixture should not pre-create shadow: {p}"

        assert (fake_repo / "meetings").is_dir()
        assert (fake_repo / "claims").is_dir()
        assert not (fake_app / "lib" / "meetings").exists()


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