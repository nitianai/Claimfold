"""P6-4: init guest template must match production and exclude deprecated models."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from unittest import mock

from council.config import CONFIG_FILE, INIT_CONFIG_TEMPLATE
from council.commands.init_cmd import cmd_init

# Retired OpenRouter / opencode slugs (audit report §12).
DEPRECATED_MODEL_FRAGMENTS = (
    "mimo-v2.5-free",
    "laguna-m.1:free",
    "poolside/laguna",
    "gemma-4-26b",
    "nemotron-120b",
    "llama-3.3-70b",
)


def _normalize_guest_yaml(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        if line.startswith("# Copy of production") or line.startswith("# Keep in sync"):
            continue
        kept.append(line)
    return "\n".join(kept).strip() + "\n"


def test_guest_template_matches_production():
    prod = CONFIG_FILE.read_text(encoding="utf-8")
    template = INIT_CONFIG_TEMPLATE.read_text(encoding="utf-8")
    assert _normalize_guest_yaml(template) == _normalize_guest_yaml(prod)


def test_guest_configs_exclude_deprecated_models():
    for path in (CONFIG_FILE, INIT_CONFIG_TEMPLATE):
        text = path.read_text(encoding="utf-8").lower()
        for frag in DEPRECATED_MODEL_FRAGMENTS:
            assert frag not in text, f"{path.name} still references deprecated model: {frag}"


def test_laguna_uses_grok_script_not_legacy_opencode():
    for path in (CONFIG_FILE, INIT_CONFIG_TEMPLATE):
        text = path.read_text(encoding="utf-8")
        assert "run_grok_guest.sh" in text
        assert "laguna-m.1" not in text


def test_cmd_init_writes_template_guests_yaml():
    with tempfile.TemporaryDirectory() as tmp:
        fake_repo = Path(tmp)
        fake_app = fake_repo / "apps" / "research_council"
        for name in ("config", "prompts", "prompts/guest", "prompts/system", "prompts/reports", "scripts", "lib"):
            (fake_app / name).mkdir(parents=True, exist_ok=True)
        (fake_repo / "docs").mkdir()
        (fake_repo / "docs" / "archive").mkdir()
        (fake_repo / "meetings").mkdir()
        (fake_app / "config" / "guests.yaml.template").write_text(
            INIT_CONFIG_TEMPLATE.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        with (
            mock.patch("council.commands.init_cmd.APP_ROOT", fake_app),
            mock.patch("council.commands.init_cmd.REPO_ROOT", fake_repo),
            mock.patch("council.commands.init_cmd.DATA_ROOT", fake_repo),
            mock.patch("council.commands.init_cmd.CONFIG_FILE", fake_app / "config" / "guests.yaml"),
            mock.patch("council.commands.init_cmd.INIT_CONFIG_TEMPLATE", fake_app / "config" / "guests.yaml.template"),
            mock.patch("council.commands.init_cmd.GUEST_TEMPLATE", fake_app / "prompts" / "guest" / "template.md"),
            mock.patch("council.commands.init_cmd.SUMMARIZER_TEMPLATE", fake_app / "prompts" / "system" / "summarizer.md"),
            mock.patch("council.commands.init_cmd.ensure_claims_dir"),
        ):
            cmd_init(argparse.Namespace())

        created = fake_app / "config" / "guests.yaml"
        assert created.is_file()
        body = created.read_text(encoding="utf-8").lower()
        for frag in DEPRECATED_MODEL_FRAGMENTS:
            assert frag not in body
        assert "gptoss20" in body
        assert "run_grok_guest.sh" in body