"""Grok guest script and guests.yaml wiring."""

from __future__ import annotations

from pathlib import Path

from council.config import APP_ROOT, SCRIPTS_DIR
from council.guests import load_guests


def test_run_grok_guest_script_exists():
    script = SCRIPTS_DIR / "run_grok_guest.sh"
    assert script.is_file(), f"missing {script}"


def test_laguna_guest_uses_grok_build_script():
    guests = load_guests()
    laguna = guests.get("laguna", {})
    assert "run_grok_guest.sh" in laguna.get("command", "")
    assert laguna.get("model") == "hermes-grok/grok-4.3"


def test_grok_guest_script_is_executable_or_bash():
    script = APP_ROOT / "scripts" / "run_grok_guest.sh"
    text = script.read_text(encoding="utf-8")
    assert '-p "$PROMPT"' in text
    assert "hermes-grok/grok-4.3" in text or "GROK_GUEST_MODEL" in text