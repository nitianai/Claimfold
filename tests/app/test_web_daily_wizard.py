"""Web daily startup wizard — static asset contract."""

from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "apps" / "research_council" / "web" / "static"


def test_daily_wizard_html_contract():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for marker in (
        'id="daily-wizard"',
        'id="wizard-steps"',
        'id="btn-daily-launch"',
        'data-step="topic"',
        'data-step="scope"',
        'data-step="guests"',
        'data-step="launch"',
        'value="research" selected',
    ):
        assert marker in html, f"missing {marker}"


def test_daily_wizard_js_contract():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for marker in (
        "DAILY_PRESET_GUESTS",
        "rates-strategist",
        "quant-researcher",
        "industry-analyst",
        "runDailyLaunch",
        "renderWizardSteps",
        "waitForTaskIdle",
    ):
        assert marker in js, f"missing {marker}"