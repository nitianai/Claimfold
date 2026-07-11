"""Phase 0 contract artifacts exist."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_platform_readme_exists():
    readme = ROOT / "platform" / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    for needle in (
        "单一事实源",
        "missionos.ledger",
        "missionos.plan",
        "plan/runtime.py",
        "ClaimLedgerAdapter",
        "文档规范",
    ):
        assert needle in text, f"missing contract section: {needle}"


def test_platform_pyproject_exists():
    pyproject = ROOT / "platform" / "pyproject.toml"
    assert pyproject.is_file()
    text = pyproject.read_text(encoding="utf-8")
    assert 'name = "missionos"' in text


def test_split_plan_documents_phase0():
    doc = ROOT / "docs" / "PLATFORM_APP_SPLIT.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "Phase 0" in text
    assert "CONDITIONAL GO" in text
    assert "文档规范" in text


def test_structure_doc_has_writing_standard():
    doc = ROOT / "docs" / "STRUCTURE.md"
    text = doc.read_text(encoding="utf-8")
    assert "文档书写规范" in text
    assert "English Term（中文名称）" in text or "English（中文）" in text


def test_app_adapters_present():
    """Phase 2: App Adapter（应用适配器）层已落地。"""
    app_root = ROOT / "apps" / "research_council"
    adapters = [
        app_root / "lib" / "council" / "adapters" / "claim_ledger.py",
        app_root / "lib" / "council" / "adapters" / "plan_runtime.py",
        app_root / "lib" / "council" / "adapters" / "executor_policy.py",
        app_root / "lib" / "council" / "adapters" / "session_adapter.py",
    ]
    for path in adapters:
        assert path.is_file(), f"missing adapter: {path}"
    plan_rt = (app_root / "lib" / "council" / "adapters" / "plan_runtime.py").read_text(encoding="utf-8")
    assert "council.guests" in plan_rt, "plan_runtime must remain App-coupled per contract"
    guest_cfg = app_root / "config" / "guest_aliases.yaml"
    assert guest_cfg.is_file(), "guest_aliases.yaml required after Phase 2"
    focus_cfg = app_root / "config" / "focus_rules.yaml"
    assert focus_cfg.is_file(), "focus_rules.yaml required after Phase 4"
    executor_map = app_root / "config" / "bindings" / "executor-guest.yaml"
    assert executor_map.is_file(), "executor-guest.yaml required after Phase 4"