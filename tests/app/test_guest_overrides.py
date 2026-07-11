"""Per-meeting guest override tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from council.guest_overrides import merge_guest_config, save_overrides
from council.guests import load_guests, load_guests_for_meeting


def test_merge_guest_config_applies_meeting_overrides():
    base = {
        "laguna": {
            "role": "Original",
            "role_id": "geo",
            "model": "old-model",
            "command": "old-cmd",
            "enabled": True,
        }
    }
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-120000"
        meeting_dir.mkdir(parents=True)
        save_overrides(
            meeting_dir,
            {
                "guests": {
                    "laguna": {
                        "role": "Grok 地缘",
                        "model": "hermes-grok/grok-4.3",
                        "command": "bash scripts/run_grok_guest.sh",
                    }
                },
                "invited": ["laguna"],
            },
        )
        merged = merge_guest_config(base, meeting_dir)
        assert merged["laguna"]["role"] == "Grok 地缘"
        assert merged["laguna"]["model"] == "hermes-grok/grok-4.3"
        assert merged["laguna"]["role_id"] == "geo"


def test_load_guests_for_meeting_integration():
    with tempfile.TemporaryDirectory() as tmp:
        meeting_dir = Path(tmp) / "meet-20260711-120000"
        meeting_dir.mkdir(parents=True)
        base_laguna = load_guests().get("laguna", {})
        save_overrides(
            meeting_dir,
            {"guests": {"laguna": {"role": "Session Role Override"}}, "invited": ["laguna"]},
        )
        merged = load_guests_for_meeting(meeting_dir)
        assert merged["laguna"]["role"] == "Session Role Override"
        assert merged["laguna"]["model"] == base_laguna.get("model")