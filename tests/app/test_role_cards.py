"""Role card library and meeting invite integration."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from council.guest_overrides import load_overrides
from council.web.role_cards import (
    card_guest_id,
    card_to_guest_patch,
    create_role_card,
    delete_role_card,
    get_role_card,
    list_role_cards,
    update_role_card,
)
from council.web.service import CouncilWebService


def test_preset_cards_have_persona_names():
    cards = list_role_cards()
    presets = [c for c in cards if c["source"] == "preset"]
    assert len(presets) >= 5
    names = {c["name"] for c in presets}
    assert "宏观策略师" in names
    assert "风险控制官" in names
    assert "价值投资人" in names
    for card in presets:
        assert card.get("model_label")
        assert card.get("rules")


def test_create_update_delete_custom_card():
    with tempfile.TemporaryDirectory() as tmp:
        cards_path = Path(tmp) / "role_cards.yaml"
        cards_path.write_text("role_cards: {}\n", encoding="utf-8")
        with patch("council.web.role_cards.ROLE_CARDS_FILE", cards_path):
            created = create_role_card(
                {
                    "name": "逆向风险官",
                    "executor_id": "claude",
                    "domain": "风险控制官",
                    "style": "审慎、反共识、先问风险",
                    "rules": "必须先给判断，再给证据。",
                    "memory": "长期偏保守",
                }
            )
            assert created["id"] == "逆向风险官"
            assert created["source"] == "custom"
            assert get_role_card("逆向风险官") is not None

            updated = update_role_card("逆向风险官", {"rules": "更新后的规则"})
            assert "更新后的规则" in updated["rules"]

            patch_data = card_to_guest_patch(updated)
            assert patch_data["card_id"] == "逆向风险官"
            assert patch_data["card_name"] == "逆向风险官"
            assert "发言规则" in patch_data["role"]
            assert card_guest_id(updated) == "rc-逆向风险官"

            delete_role_card("逆向风险官")
            assert get_role_card("逆向风险官") is None


def test_start_meeting_with_invited_role_cards():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        meetings_dir = tmp_path / "meetings"
        meetings_dir.mkdir()
        current_file = tmp_path / ".current_meeting"
        cards_path = tmp_path / "role_cards.yaml"
        cards_path.write_text("role_cards: {}\n", encoding="utf-8")

        patches = [
            patch("council.config.MEETINGS_DIR", meetings_dir),
            patch("council.config.CURRENT_MEETING_FILE", current_file),
            patch("council.web.service.MEETINGS_DIR", meetings_dir),
            patch("council.web.service.CURRENT_MEETING_FILE", current_file),
            patch("council.commands.meeting_start.MEETINGS_DIR", meetings_dir),
            patch("council.commands.meeting_start.CURRENT_MEETING_FILE", current_file),
            patch("council.web.role_cards.ROLE_CARDS_FILE", cards_path),
        ]
        for p in patches:
            p.start()
        try:
            card = create_role_card(
                {
                    "name": "测试嘉宾",
                    "executor_id": "codex",
                    "domain": "宏观策略师",
                    "style": "冷静、中立、重证据",
                    "rules": "结构化发言",
                }
            )

            svc = CouncilWebService()
            result = svc.start_meeting(
                topic="角色卡邀请测试",
                mode="interactive",
                invited_card_ids=[card["id"]],
                run_context_after=False,
            )
            assert result["ok"] is True
            meeting = result["meeting"]
            assert card["id"] in meeting["invited_cards"]

            meeting_dir = meetings_dir / meeting["meeting_id"]
            overrides = load_overrides(meeting_dir)
            assert f"rc-{card['id']}" in overrides["invited"]
            guest_patch = overrides["guests"][f"rc-{card['id']}"]
            assert guest_patch["card_name"] == "测试嘉宾"

            invite_result = svc.invite_role_card("risk-officer")
            assert invite_result["ok"] is True
            assert "risk-officer" in invite_result["meeting"]["invited_cards"]
        finally:
            for p in reversed(patches):
                p.stop()