"""Hosting catalog — roles, executors, guest templates for web setup UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from council.config import CONFIG_FILE, EXECUTORS_FILE, ROLES_FILE
from council.executor_guest import EXECUTOR_TO_GUEST
from council.guest_overrides import load_overrides
from council.guests import guest_roster, load_guests


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _executor_command(executor: dict[str, Any]) -> str:
    model = str(executor.get("model", ""))
    parts = executor.get("command_template") or []
    if not isinstance(parts, list):
        return ""
    rendered = [str(p).replace("{model}", model) for p in parts]
    return " ".join(rendered)


def build_hosting_catalog() -> dict[str, Any]:
    guests_raw = load_guests()
    with CONFIG_FILE.open(encoding="utf-8") as f:
        root_cfg = yaml.safe_load(f) or {}
    max_parallel = int(root_cfg.get("max_parallel", 6))

    roles_data = _load_yaml(ROLES_FILE).get("roles", {})
    role_options: list[dict[str, str]] = []
    seen_roles: set[str] = set()
    for rid, rdef in roles_data.items():
        if isinstance(rdef, dict):
            role_options.append(
                {"role_id": rid, "name": str(rdef.get("name", rid)), "purpose": str(rdef.get("purpose", ""))}
            )
            seen_roles.add(rid)
    for gid, gdef in guests_raw.items():
        rid = str(gdef.get("role_id", ""))
        if rid and rid not in seen_roles:
            role_options.append({"role_id": rid, "name": rid, "purpose": str(gdef.get("role", ""))[:80]})
            seen_roles.add(rid)

    executors_data = _load_yaml(EXECUTORS_FILE).get("executors", {})
    executor_options: list[dict[str, Any]] = []
    for eid, edef in executors_data.items():
        if not isinstance(edef, dict) or not edef.get("enabled", True):
            continue
        executor_options.append(
            {
                "executor_id": eid,
                "model": str(edef.get("model", "")),
                "command": _executor_command(edef),
                "adapter": str(edef.get("adapter", "")),
                "default_guest": EXECUTOR_TO_GUEST.get(eid, ""),
            }
        )

    guest_templates: list[dict[str, Any]] = []
    for gid, gdef in guests_raw.items():
        if gdef.get("reporter") or gdef.get("summarizer") or gid in ("summarizer", "reporter", "context_collector"):
            continue
        guest_templates.append(
            {
                "id": gid,
                "role": str(gdef.get("role", gid)),
                "role_id": str(gdef.get("role_id", gid)),
                "model": str(gdef.get("model", "")),
                "command": str(gdef.get("command", "")),
                "model_tier": str(gdef.get("model_tier", "")),
                "guest_type": str(gdef.get("guest_type", "llm")),
                "enabled": bool(gdef.get("enabled", True)),
                "allow_parallel": bool(gdef.get("allow_parallel", True)),
                "timeout_seconds": int(gdef.get("timeout_seconds", 180)),
                "executor_id": _guess_executor_id(gid, str(gdef.get("model", "")), executors_data),
            }
        )

    return {
        "max_parallel": max_parallel,
        "role_options": sorted(role_options, key=lambda r: r["role_id"]),
        "executors": executor_options,
        "guest_templates": guest_templates,
        "default_invited": ["macro-strategist", "risk-officer"],
    }


def _guess_executor_id(guest_id: str, model: str, executors: dict[str, Any]) -> str:
    for eid, guest in EXECUTOR_TO_GUEST.items():
        if guest == guest_id:
            return eid
    for eid, edef in executors.items():
        if isinstance(edef, dict) and str(edef.get("model", "")) == model:
            return eid
    return ""


def meeting_guest_setup(meeting_dir: Path) -> dict[str, Any]:
    catalog = build_hosting_catalog()
    overrides = load_overrides(meeting_dir)
    base = load_guests()
    merged = {gid: dict(base[gid]) for gid in base}
    for gid, patch in (overrides.get("guests") or {}).items():
        if gid in merged and isinstance(patch, dict):
            merged[gid].update(patch)

    rows: list[dict[str, Any]] = []
    for tmpl in catalog["guest_templates"]:
        gid = tmpl["id"]
        cfg = merged.get(gid, tmpl)
        patch = (overrides.get("guests") or {}).get(gid) or {}
        rows.append(
            {
                "id": gid,
                "invited": gid in (overrides.get("invited") or []),
                "role": cfg.get("role", tmpl["role"]),
                "role_id": cfg.get("role_id", tmpl["role_id"]),
                "model": cfg.get("model", tmpl["model"]),
                "command": cfg.get("command", tmpl["command"]),
                "executor_id": cfg.get("executor_id", tmpl.get("executor_id", "")),
                "enabled": cfg.get("enabled", tmpl["enabled"]),
                "allow_parallel": cfg.get("allow_parallel", tmpl["allow_parallel"]),
                "timeout_seconds": cfg.get("timeout_seconds", tmpl["timeout_seconds"]),
                "model_tier": cfg.get("model_tier", tmpl["model_tier"]),
                "card_id": patch.get("card_id", gid if gid in {t["id"] for t in catalog["guest_templates"]} else ""),
                "card_name": patch.get("card_name", ""),
                "card_summary": patch.get("card_summary", ""),
            }
        )

    for gid in overrides.get("invited") or []:
        if any(r["id"] == gid for r in rows):
            continue
        patch = (overrides.get("guests") or {}).get(gid) or {}
        rows.append(
            {
                "id": gid,
                "invited": True,
                "role": patch.get("role", gid),
                "role_id": patch.get("role_id", gid),
                "model": patch.get("model", ""),
                "command": patch.get("command", ""),
                "executor_id": patch.get("executor_id", ""),
                "enabled": True,
                "allow_parallel": True,
                "timeout_seconds": int(patch.get("timeout_seconds", 180)),
                "model_tier": patch.get("model_tier", "llm"),
                "card_id": patch.get("card_id", ""),
                "card_name": patch.get("card_name", gid),
                "card_summary": patch.get("card_summary", ""),
            }
        )

    return {
        "guests": rows,
        "invited": overrides.get("invited") or [],
        "setup": overrides.get("setup") or {},
        "catalog": {
            "role_options": catalog["role_options"],
            "executors": catalog["executors"],
            "max_parallel": catalog["max_parallel"],
        },
    }


def apply_executor_binding(executor_id: str, executors: list[dict[str, Any]]) -> dict[str, str]:
    for ex in executors:
        if ex.get("executor_id") == executor_id:
            return {
                "model": ex.get("model", ""),
                "command": ex.get("command", ""),
                "executor_id": executor_id,
                "default_guest": str(ex.get("default_guest", "")),
            }
    return {"model": "", "command": "", "executor_id": executor_id, "default_guest": ""}