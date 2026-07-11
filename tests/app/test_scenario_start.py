"""PR2: --scenario / --bind / --bindings CLI wiring tests."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

from council.config import APP_ROOT, MEETING_PLAN_FILENAME, REPO_ROOT
from council.plan import (
    PlanValidationError,
    build_meeting_plan,
    load_meeting_plan,
    parse_cli_bindings,
    resolve_scenario_path,
    validate_plan,
)
from council.guests import guest_roster, load_guests, resolve_executor_to_guest
from council.plan.paths import resolve_bindings_path

FIXTURE_BINDINGS = REPO_ROOT / "tests" / "fixtures" / "plan" / "project-bindings.yaml"


def test_resolve_executor_to_guest_maps_plan_executors():
    roster = guest_roster(load_guests())
    assert resolve_executor_to_guest("codex", roster) == "codex"
    assert resolve_executor_to_guest("claude", roster) == "claude_sonnet"
    assert resolve_executor_to_guest("qwen_local", roster) == "qwen"
    assert resolve_executor_to_guest("grok", roster) == "laguna"


def test_parse_cli_bindings_ok():
    assert parse_cli_bindings(["architect=claude", "moderator=qwen_local"]) == {
        "architect": "claude",
        "moderator": "qwen_local",
    }


def test_parse_cli_bindings_duplicate_fails():
    try:
        parse_cli_bindings(["architect=claude", "architect=codex"])
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "duplicate" in str(exc)


def test_parse_cli_bindings_bad_syntax_fails():
    try:
        parse_cli_bindings(["architect-claude"])
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "invalid --bind" in str(exc)


def test_resolve_scenario_path_accepts_underscore_slug():
    path = resolve_scenario_path("project_development")
    assert path.name == "project-development.yaml"
    assert path.is_file()


def test_resolve_bindings_path_explicit():
    path = resolve_bindings_path("project-development", FIXTURE_BINDINGS)
    assert path == FIXTURE_BINDINGS.resolve()


def test_resolve_bindings_path_default_config():
    path = resolve_bindings_path("project-development")
    assert path.name == "project-development.yaml"
    assert path.is_file()


def test_compile_includes_scenario_termination():
    plan = build_meeting_plan(
        scenario="project-development",
        meeting_id="meet-test-term",
        topic="termination",
        generated_at="2026-07-10T12:00:00Z",
        bindings_path=FIXTURE_BINDINGS,
    )
    assert plan["termination"]["max_rounds"] == 10
    assert plan["termination"]["pause_every_rounds"] == 3


def test_serial_roster_excludes_script_guests():
    from council.guests import guest_roster, load_guests

    guests = load_guests()
    assert "tsla_feed" in guest_roster(guests)
    assert "tsla_feed" not in guest_roster(guests, serial=True)


def test_build_meeting_plan_with_cli_bind_override():
    plan = build_meeting_plan(
        scenario="project-development",
        meeting_id="meet-test-bind",
        topic="bind override",
        generated_at="2026-07-10T12:00:00Z",
        bindings_path=FIXTURE_BINDINGS,
        cli_bindings={"architect": "codex"},
    )
    architect = next(p for p in plan["participants"] if p["role_id"] == "architect")
    assert architect["executor_id"] == "codex"
    assert plan["provenance"]["bindings_source"] == "cli+file"
    validate_plan(plan)


def test_build_meeting_plan_missing_binding_fails():
    bindings = Path(tempfile.mkdtemp()) / "partial.yaml"
    bindings.write_text(
        "bindings:\n  moderator: qwen_local\n  architect: claude\n",
        encoding="utf-8",
    )
    try:
        build_meeting_plan(
            scenario="project-development",
            meeting_id="meet-test-miss",
            topic="missing bindings",
            generated_at="2026-07-10T12:00:00Z",
            bindings_path=bindings,
        )
        raise AssertionError("expected PlanValidationError")
    except PlanValidationError as exc:
        assert "recorder" in str(exc) or "no executor binding" in str(exc)


def test_scenario_start_writes_meeting_plan_json():
    from argparse import Namespace

    from council.commands.meeting_start import cmd_start
    from council.config import MEETINGS_DIR

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        meetings = root / "meetings"
        meetings.mkdir()
        pointer = root / ".current_meeting"
        scenario_dir = root / "scenarios"
        scenario_dir.mkdir()
        (scenario_dir / "project-development.yaml").write_text(
            (APP_ROOT / "scenarios" / "project-development.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        config_dir = root / "config"
        (config_dir / "bindings").mkdir(parents=True)
        for name in ("roles.yaml", "executors.yaml"):
            (config_dir / name).write_text(
                (APP_ROOT / "config" / name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        (config_dir / "bindings" / "project-development.yaml").write_text(
            FIXTURE_BINDINGS.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        import council.config as cfg
        import council.commands.meeting_start as start_mod

        old = (
            cfg.ROOT,
            cfg.MEETINGS_DIR,
            cfg.CURRENT_MEETING_FILE,
            cfg.SCENARIOS_DIR,
            cfg.ROLES_FILE,
            cfg.EXECUTORS_FILE,
            cfg.BINDINGS_DIR,
            start_mod.MEETINGS_DIR,
            start_mod.CURRENT_MEETING_FILE,
        )
        cfg.ROOT = root
        cfg.MEETINGS_DIR = meetings
        cfg.CURRENT_MEETING_FILE = pointer
        cfg.SCENARIOS_DIR = scenario_dir
        cfg.ROLES_FILE = config_dir / "roles.yaml"
        cfg.EXECUTORS_FILE = config_dir / "executors.yaml"
        cfg.BINDINGS_DIR = config_dir / "bindings"
        start_mod.MEETINGS_DIR = meetings
        start_mod.CURRENT_MEETING_FILE = pointer
        try:
            args = Namespace(
                topic="PR2 smoke",
                question=None,
                rounds_before_owner=3,
                mode="standard",
                max_rounds=None,
                stale_limit=5,
                scenario="project-development",
                bindings=None,
                bind=["architect=codex"],
            )
            cmd_start(args)
            meeting_id = pointer.read_text(encoding="utf-8").strip()
            meeting_dir = meetings / meeting_id
            plan_path = meeting_dir / MEETING_PLAN_FILENAME
            assert plan_path.is_file()
            plan = load_meeting_plan(plan_path)
            architect = next(p for p in plan["participants"] if p["role_id"] == "architect")
            assert architect["executor_id"] == "codex"
            state = json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))
            assert state["scenario_id"] == "project_development"
            assert state["meeting_plan_file"] == MEETING_PLAN_FILENAME
            assert state["participant_ids"]
            assert state["max_rounds"] == 10
            assert state["max_round_before_owner"] == 3
            assert state["plan_actor_queue"]
            assert state["next_speaker"] == state["plan_actor_queue"][0]
        finally:
            (
                cfg.ROOT,
                cfg.MEETINGS_DIR,
                cfg.CURRENT_MEETING_FILE,
                cfg.SCENARIOS_DIR,
                cfg.ROLES_FILE,
                cfg.EXECUTORS_FILE,
                cfg.BINDINGS_DIR,
                start_mod.MEETINGS_DIR,
                start_mod.CURRENT_MEETING_FILE,
            ) = old


def test_bindings_without_scenario_rejected():
    from argparse import Namespace

    from council.commands.meeting_start import cmd_start

    args = Namespace(
        topic="bad flags",
        question=None,
        rounds_before_owner=3,
        mode="standard",
        max_rounds=None,
        stale_limit=5,
        scenario=None,
        bindings="config/bindings/project-development.yaml",
        bind=None,
    )
    try:
        cmd_start(args)
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert "requires --scenario" in str(exc)