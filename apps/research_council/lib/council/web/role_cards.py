"""Role card library — builtin guests + user-defined cards for Web UI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from council.config import CONFIG_FILE
from council.web.hosting import apply_executor_binding, build_hosting_catalog

ROLE_CARDS_FILE = CONFIG_FILE.parent / "role_cards.yaml"
ROLE_PRESETS_FILE = CONFIG_FILE.parent / "role_card_presets.yaml"
_DOMAIN_KIND = {
    "风险控制官": "risk",
    "宏观策略师": "arch",
    "价值投资人": "product",
    "量化研究员": "ops",
    "行业研究员": "arch",
}
_DOMAIN_ROLE_ID = {
    "风险控制官": "logic_auditor",
    "宏观策略师": "macro_strategist",
    "价值投资人": "equity_strategist",
    "量化研究员": "oss_reasoner",
    "行业研究员": "energy_analyst",
}
_ROLE_ID_DOMAIN = {v: k for k, v in _DOMAIN_ROLE_ID.items()}


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip().lower())
    return s.strip("-")[:48] or "role"


def _load_custom_cards() -> dict[str, dict[str, Any]]:
    if not ROLE_CARDS_FILE.is_file():
        return {}
    with ROLE_CARDS_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    cards = data.get("role_cards") or {}
    return cards if isinstance(cards, dict) else {}


def _save_custom_cards(cards: dict[str, dict[str, Any]]) -> None:
    ROLE_CARDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ROLE_CARDS_FILE.open("w", encoding="utf-8") as f:
        yaml.dump({"role_cards": cards}, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _model_label(model: str, executor_id: str = "") -> str:
    m = model.lower()
    if "claude" in m:
        return "Claude"
    if "codex" in m or "gpt" in m:
        return "GPT / Codex"
    if "grok" in m:
        return "Grok"
    if "qwen" in m:
        return "Qwen"
    if "gemini" in m:
        return "Gemini"
    if "llama" in m or "deepseek" in m:
        return "Llama"
    if "nemotron" in m:
        return "Nemotron"
    if "cohere" in m or "north" in m:
        return "North"
    if executor_id == "codex":
        return "GPT / Codex"
    if executor_id == "claude":
        return "Claude"
    if executor_id == "grok":
        return "Grok"
    if executor_id == "qwen_local":
        return "Qwen"
    return model.split("/")[-1] if model else "自定义"


def _guest_template_index() -> dict[str, dict[str, Any]]:
    catalog = build_hosting_catalog()
    return {str(t["id"]): t for t in catalog.get("guest_templates", [])}


def _load_preset_raw() -> dict[str, dict[str, Any]]:
    if not ROLE_PRESETS_FILE.is_file():
        return {}
    with ROLE_PRESETS_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    presets = data.get("presets") or {}
    return presets if isinstance(presets, dict) else {}


def _preset_cards() -> list[dict[str, Any]]:
    templates = _guest_template_index()
    cards: list[dict[str, Any]] = []
    for preset_id, raw in _load_preset_raw().items():
        if not isinstance(raw, dict):
            continue
        base_guest = str(raw.get("base_guest") or "")
        tmpl = templates.get(base_guest) or {}
        if not tmpl.get("enabled", True):
            continue
        card = _normalize_custom(
            preset_id,
            {
                **raw,
                "id": preset_id,
                "model": raw.get("model") or tmpl.get("model", ""),
                "command": raw.get("command") or tmpl.get("command", ""),
                "executor_id": raw.get("executor_id") or tmpl.get("executor_id", ""),
                "base_guest": base_guest or preset_id,
            },
        )
        card["source"] = "preset"
        card["model_label"] = str(raw.get("model_label") or _model_label(card.get("model", ""), card.get("executor_id", "")))
        cards.append(card)
    return cards


def _builtin_cards() -> list[dict[str, Any]]:
    """Legacy guest-id cards — kept for resolving old meeting invites."""
    catalog = build_hosting_catalog()
    cards: list[dict[str, Any]] = []
    for tmpl in catalog.get("guest_templates", []):
        gid = tmpl["id"]
        role_text = str(tmpl.get("role", gid))
        role_id = str(tmpl.get("role_id", gid))
        domain = _ROLE_ID_DOMAIN.get(role_id, "")
        if not domain:
            name = role_text.split("—")[0].strip() if "—" in role_text else role_text.split("-")[0].strip()
            domain = name
        display_name = domain or gid
        model = str(tmpl.get("model", ""))
        cards.append(
            {
                "id": gid,
                "source": "builtin",
                "name": display_name,
                "base_guest": gid,
                "role": role_text,
                "role_id": role_id,
                "model": model,
                "model_label": _model_label(model, str(tmpl.get("executor_id", ""))),
                "command": str(tmpl.get("command", "")),
                "executor_id": str(tmpl.get("executor_id", "")),
                "style": "冷静、中立、重证据",
                "domain": domain or role_id,
                "kind": _DOMAIN_KIND.get(display_name, "arch"),
                "rules": "",
                "memory": "",
                "summary": role_text[:160],
                "enabled": bool(tmpl.get("enabled", True)),
            }
        )
    return cards


def _normalize_custom(card_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    catalog = build_hosting_catalog()
    executors = catalog.get("executors") or []
    executor_id = str(raw.get("executor_id") or "")
    binding = apply_executor_binding(executor_id, executors) if executor_id else {}
    base_guest = str(raw.get("base_guest") or binding.get("default_guest") or "codex")
    domain = str(raw.get("domain") or "宏观策略师")
    name = str(raw.get("name") or card_id).strip()
    style = str(raw.get("style") or "")
    rules = str(raw.get("rules") or "").strip()
    memory = str(raw.get("memory") or "").strip()
    model = str(raw.get("model") or binding.get("model") or "")
    command = str(raw.get("command") or binding.get("command") or "")
    role_id = str(raw.get("role_id") or _DOMAIN_ROLE_ID.get(domain, "macro_strategist"))
    role = f"{name} — {domain}"
    if style:
        role += f"（{style}）"
    summary = str(raw.get("summary") or "").strip()
    if not summary:
        summary = f"{domain} · {style or '自定义角色'}。{rules[:120]}"
    source = str(raw.get("source") or "custom")
    return {
        "id": card_id,
        "source": source,
        "name": name,
        "base_guest": base_guest,
        "role": role,
        "role_id": role_id,
        "model": model,
        "model_label": _model_label(model, executor_id),
        "command": command,
        "executor_id": executor_id,
        "style": style,
        "domain": domain,
        "kind": str(raw.get("kind") or _DOMAIN_KIND.get(domain, "arch")),
        "rules": rules,
        "memory": memory,
        "summary": summary,
        "enabled": True,
    }


def list_role_cards() -> list[dict[str, Any]]:
    presets = _preset_cards()
    custom = [_normalize_custom(cid, raw) for cid, raw in _load_custom_cards().items()]
    seen = {c["id"] for c in presets}
    merged = list(presets)
    for card in custom:
        if card["id"] not in seen:
            merged.append(card)
            seen.add(card["id"])
    return merged


def get_role_card(card_id: str) -> dict[str, Any] | None:
    for card in list_role_cards():
        if card["id"] == card_id:
            return card
    for card in _builtin_cards():
        if card["id"] == card_id:
            return card
    return None


def card_guest_id(card: dict[str, Any]) -> str:
    if card.get("source") == "builtin":
        return str(card["id"])
    return f"rc-{card['id']}"


def card_to_guest_patch(card: dict[str, Any]) -> dict[str, Any]:
    rules = str(card.get("rules") or "").strip()
    memory = str(card.get("memory") or "").strip()
    role = str(card.get("role") or card.get("name") or "")
    if rules or memory:
        extra = []
        if rules:
            extra.append(f"发言规则：{rules}")
        if memory:
            extra.append(f"角色偏好：{memory}")
        role = f"{role}\n" + "\n".join(extra)
    return {
        "role": role,
        "role_id": card.get("role_id", ""),
        "model": card.get("model", ""),
        "command": card.get("command", ""),
        "executor_id": card.get("executor_id", ""),
        "enabled": True,
        "allow_parallel": True,
        "guest_type": "llm",
        "base_guest": card.get("base_guest", ""),
        "card_id": card.get("id"),
        "card_name": card.get("name"),
        "card_summary": card.get("summary"),
    }


def create_role_card(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("角色名称不能为空")
    card_id = str(payload.get("id") or "").strip() or _slugify(name)
    reserved = {c["id"] for c in _builtin_cards()} | {c["id"] for c in _preset_cards()}
    if card_id in reserved:
        raise ValueError(f"与已有角色冲突: {card_id}")
    custom = _load_custom_cards()
    if card_id in custom and not payload.get("replace"):
        raise ValueError(f"角色卡已存在: {card_id}")
    card = _normalize_custom(card_id, payload)
    custom[card_id] = {
        k: card[k]
        for k in (
            "name",
            "base_guest",
            "executor_id",
            "model",
            "command",
            "style",
            "domain",
            "kind",
            "rules",
            "memory",
            "summary",
            "role_id",
        )
        if k in card
    }
    _save_custom_cards(custom)
    return card


def update_role_card(card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if card_id in {c["id"] for c in _preset_cards()} or card_id in {c["id"] for c in _builtin_cards()}:
        raise ValueError("预设角色不可直接编辑，请创建新角色卡")
    custom = _load_custom_cards()
    if card_id not in custom:
        raise ValueError(f"角色卡不存在: {card_id}")
    merged = {**custom[card_id], **payload, "id": card_id}
    card = _normalize_custom(card_id, merged)
    custom[card_id] = {
        k: card[k]
        for k in (
            "name",
            "base_guest",
            "executor_id",
            "model",
            "command",
            "style",
            "domain",
            "kind",
            "rules",
            "memory",
            "summary",
            "role_id",
        )
        if k in card
    }
    _save_custom_cards(custom)
    return card


def delete_role_card(card_id: str) -> None:
    if card_id in {c["id"] for c in _preset_cards()} or card_id in {c["id"] for c in _builtin_cards()}:
        raise ValueError("预设角色不可删除")
    custom = _load_custom_cards()
    if card_id not in custom:
        raise ValueError(f"角色卡不存在: {card_id}")
    del custom[card_id]
    _save_custom_cards(custom)