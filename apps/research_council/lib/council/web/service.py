"""Council web service — wraps CLI operations for the chat UI."""

from __future__ import annotations

import argparse
import io
import json
import sys
import threading
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from council.commands.daily_context import cmd_context
from council.commands.meeting_owner import cmd_ask, cmd_continue, cmd_stop, cmd_view
from council.commands.meeting_run import cmd_run_interactive, cmd_run_parallel, cmd_select
from council.interactive.annotations import build_session_annotations
from council.interactive.state import is_interactive_mode, session_inspect_payload
from council.commands.meeting_start import cmd_start
from council.config import CONFIG_FILE, CURRENT_MEETING_FILE, DATA_ROOT, MEETINGS_DIR

from council.guests import guest_roster, load_guests, load_guests_for_meeting
from council.guest_aliases import GUEST_ALIASES
from council.state_store import load_state, save_state
from council.guest_overrides import load_overrides, save_overrides
from council.web.chat import build_chat_feed, build_council_status, build_guest_positions
from council.web.hosting import build_hosting_catalog, meeting_guest_setup
from council.web.role_cards import (
    card_guest_id,
    card_to_guest_patch,
    create_role_card,
    delete_role_card,
    get_role_card,
    list_role_cards,
    update_role_card,
)
from missionos.utils import validate_meeting_id


class CouncilWebService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._task: str | None = None
        self._task_error: str | None = None

    def task_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._task is not None,
                "task": self._task,
                "error": self._task_error,
            }

    def _set_task(self, name: str | None, *, error: str | None = None) -> None:
        with self._lock:
            self._task = name
            self._task_error = error

    def _run_bg(self, name: str, fn) -> dict[str, Any]:
        with self._lock:
            if self._task:
                return {"ok": False, "error": f"任务进行中: {self._task}"}

        def worker() -> None:
            self._set_task(name)
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    fn()
                self._set_task(None)
            except SystemExit as exc:
                self._set_task(None, error=str(exc) or "操作失败")
            except Exception as exc:
                self._set_task(None, error=str(exc))

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "task": name}

    def try_current_meeting_dir(self) -> Path | None:
        if not CURRENT_MEETING_FILE.exists():
            return None
        try:
            meeting_id = validate_meeting_id(CURRENT_MEETING_FILE.read_text(encoding="utf-8").strip())
        except SystemExit:
            return None
        meeting_dir = MEETINGS_DIR / meeting_id
        return meeting_dir if meeting_dir.is_dir() else None

    def list_meetings(self) -> list[dict[str, Any]]:
        current = self.try_current_meeting_dir()
        current_id = current.name if current else ""
        items: list[dict[str, Any]] = []
        if not MEETINGS_DIR.is_dir():
            return items
        for path in sorted(MEETINGS_DIR.glob("meet-*"), reverse=True):
            if not path.is_dir() or path.name.startswith("meet-_"):
                continue
            try:
                state = load_state(path)
            except (OSError, json.JSONDecodeError):
                state = {}
            items.append(
                {
                    "meeting_id": path.name,
                    "topic": state.get("topic", ""),
                    "status": state.get("status", "unknown"),
                    "round": state.get("round", 0),
                    "is_current": path.name == current_id,
                }
            )
        return items

    def switch_meeting(self, meeting_id: str) -> dict[str, Any]:
        meeting_id = validate_meeting_id(meeting_id.strip())
        meeting_dir = MEETINGS_DIR / meeting_id
        if not meeting_dir.is_dir():
            return {"ok": False, "error": f"会议不存在: {meeting_id}"}
        CURRENT_MEETING_FILE.write_text(meeting_id + "\n", encoding="utf-8")
        return {"ok": True, "meeting_id": meeting_id}

    def meeting_payload(self, meeting_dir: Path | None = None) -> dict[str, Any]:
        meeting_dir = meeting_dir or self.try_current_meeting_dir()
        if meeting_dir is None:
            return {"active": False, "meetings": self.list_meetings()}

        state = load_state(meeting_dir)
        guests_cfg = load_guests_for_meeting(meeting_dir)
        roster = guest_roster(guests_cfg)
        guest_options = [
            {
                "id": gid,
                "alias": next((a for a, t in GUEST_ALIASES.items() if t == gid), gid),
                "role": guests_cfg.get(gid, {}).get("role", gid),
                "enabled": guests_cfg.get(gid, {}).get("enabled", True),
            }
            for gid in roster
        ]
        return {
            "active": True,
            "meeting_id": state.get("meeting_id", meeting_dir.name),
            "topic": state.get("topic", ""),
            "status": state.get("status", ""),
            "round": state.get("round", 0),
            "meeting_mode": state.get("meeting_mode", ""),
            "owner_required": state.get("owner_required", False),
            "selected_guests": state.get("selected_guests", []),
            "current_focus": state.get("current_focus", ""),
            "confirmed_points": state.get("confirmed_points", []),
            "conflicts": state.get("conflicts", []),
            "open_questions": state.get("open_questions", []),
            "guest_summaries": state.get("guest_summaries", {}),
            "guest_positions": build_guest_positions(meeting_dir, state, guests_cfg),
            "council_status": build_council_status(
                meeting_dir, state, guests_cfg, task=self.task_status()
            ),
            "next_question": state.get("next_question", ""),
            "chat": build_chat_feed(meeting_dir, state),
            "guests": guest_options,
            "task": self.task_status(),
            "hosting": meeting_guest_setup(meeting_dir),
            "interactive": self._interactive_payload(meeting_dir, state),
            "role_cards": list_role_cards(),
            "invited_cards": self._invited_card_ids(meeting_dir),
        }

    def _invited_card_ids(self, meeting_dir: Path) -> list[str]:
        overrides = load_overrides(meeting_dir)
        invited: list[str] = []
        for gid in overrides.get("invited") or []:
            patch = (overrides.get("guests") or {}).get(gid) or {}
            if patch.get("card_id"):
                invited.append(str(patch["card_id"]))
            else:
                invited.append(str(gid))
        return invited

    def role_cards_payload(self) -> dict[str, Any]:
        catalog = build_hosting_catalog()
        return {
            "cards": list_role_cards(),
            "catalog": {
                "executors": catalog.get("executors", []),
                "role_options": catalog.get("role_options", []),
                "domains": [
                    "风险控制官",
                    "宏观策略师",
                    "价值投资人",
                    "量化研究员",
                    "行业研究员",
                ],
                "styles": [
                    "审慎、反共识、先问风险",
                    "进攻型、机会导向、重赔率",
                    "冷静、中立、重证据",
                    "挑剔、质疑假设、找漏洞",
                ],
            },
        }

    def save_role_card(self, payload: dict[str, Any], *, card_id: str = "") -> dict[str, Any]:
        try:
            if card_id:
                card = update_role_card(card_id, payload)
            else:
                card = create_role_card(payload)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "card": card, "cards": list_role_cards()}

    def remove_role_card(self, card_id: str) -> dict[str, Any]:
        try:
            delete_role_card(card_id)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "cards": list_role_cards()}

    def _invite_card_to_meeting(self, meeting_dir: Path, card_id: str) -> str:
        card = get_role_card(card_id)
        if card is None:
            raise ValueError(f"角色卡不存在: {card_id}")
        gid = card_guest_id(card)
        overrides = load_overrides(meeting_dir)
        invited = list(overrides.get("invited") or [])
        guests = dict(overrides.get("guests") or {})
        if gid not in invited:
            invited.append(gid)
        guests[gid] = card_to_guest_patch(card)
        save_overrides(
            meeting_dir,
            {
                "guests": guests,
                "invited": invited,
                "setup": overrides.get("setup") or {},
            },
        )
        state = load_state(meeting_dir)
        state["selected_guests"] = invited
        save_state(meeting_dir, state)
        return gid

    def invite_role_card(self, card_id: str) -> dict[str, Any]:
        card_id = card_id.strip()
        if not card_id:
            return {"ok": False, "error": "card_id 不能为空"}
        meeting_dir = self.try_current_meeting_dir()
        if meeting_dir is None:
            return {"ok": False, "error": "请先创建或选择会议"}
        try:
            guest_id = self._invite_card_to_meeting(meeting_dir, card_id)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "guest_id": guest_id, "meeting": self.meeting_payload(meeting_dir)}

    def uninvite_role_card(self, card_id: str) -> dict[str, Any]:
        meeting_dir = self.try_current_meeting_dir()
        if meeting_dir is None:
            return {"ok": False, "error": "无活动会议"}
        card = get_role_card(card_id.strip())
        if card is None:
            return {"ok": False, "error": "角色卡不存在"}
        gid = card_guest_id(card)
        overrides = load_overrides(meeting_dir)
        invited = [g for g in (overrides.get("invited") or []) if g != gid]
        guests = dict(overrides.get("guests") or {})
        guests.pop(gid, None)
        save_overrides(meeting_dir, {"guests": guests, "invited": invited, "setup": overrides.get("setup") or {}})
        state = load_state(meeting_dir)
        state["selected_guests"] = invited
        save_state(meeting_dir, state)
        return {"ok": True, "meeting": self.meeting_payload(meeting_dir)}

    def _interactive_payload(self, meeting_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
        if not is_interactive_mode(state):
            return {"enabled": False}
        payload = session_inspect_payload(state)
        payload["enabled"] = True
        payload["annotations"] = build_session_annotations(meeting_dir, state)
        return payload

    def hosting_catalog(self) -> dict[str, Any]:
        return build_hosting_catalog()

    def project_config_payload(self) -> dict[str, Any]:
        catalog = build_hosting_catalog()
        guests_raw = load_guests()
        rows: list[dict[str, Any]] = []
        for tmpl in catalog["guest_templates"]:
            gid = tmpl["id"]
            cfg = guests_raw.get(gid, tmpl)
            rows.append(
                {
                    "id": gid,
                    "enabled": bool(cfg.get("enabled", tmpl.get("enabled", True))),
                    "role": cfg.get("role", tmpl["role"]),
                    "role_id": cfg.get("role_id", tmpl["role_id"]),
                    "model": cfg.get("model", tmpl["model"]),
                    "command": cfg.get("command", tmpl["command"]),
                    "executor_id": tmpl.get("executor_id", ""),
                    "allow_parallel": bool(cfg.get("allow_parallel", tmpl.get("allow_parallel", True))),
                    "timeout_seconds": int(cfg.get("timeout_seconds", tmpl.get("timeout_seconds", 180))),
                    "model_tier": str(cfg.get("model_tier", tmpl.get("model_tier", ""))),
                    "guest_type": str(cfg.get("guest_type", tmpl.get("guest_type", "llm"))),
                }
            )
        return {
            "catalog": catalog,
            "guest_rows": rows,
            "config_path": str(CONFIG_FILE),
        }

    def save_project_config(self, guest_rows: list[dict[str, Any]]) -> dict[str, Any]:
        import yaml

        if not CONFIG_FILE.is_file():
            return {"ok": False, "error": f"配置文件不存在: {CONFIG_FILE}"}
        with CONFIG_FILE.open(encoding="utf-8") as f:
            root = yaml.safe_load(f) or {}
        guests = root.get("guests")
        if not isinstance(guests, dict):
            return {"ok": False, "error": "guests.yaml 格式无效"}
        for row in guest_rows:
            gid = str(row.get("id", "")).strip()
            if not gid or gid not in guests:
                continue
            patch = {
                k: row[k]
                for k in (
                    "role",
                    "role_id",
                    "model",
                    "command",
                    "enabled",
                    "allow_parallel",
                    "timeout_seconds",
                )
                if k in row and row[k] is not None and row[k] != ""
            }
            if "enabled" in row:
                patch["enabled"] = bool(row["enabled"])
            if patch:
                guests[gid].update(patch)
        root["guests"] = guests
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            yaml.dump(root, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return {"ok": True, "config": self.project_config_payload()}

    def meeting_speak(
        self,
        *,
        mode: str = "ask",
        text: str = "",
        run_next: bool = False,
    ) -> dict[str, Any]:
        text = text.strip()
        if not text:
            return {"ok": False, "error": "内容不能为空"}
        if mode == "view":
            result = self.owner_view(text)
        else:
            result = self.owner_ask(text)
        if not result.get("ok"):
            return result
        if run_next:
            meeting_dir = self.try_current_meeting_dir()
            st = load_state(meeting_dir) if meeting_dir else {}
            runner = self.run_interactive if is_interactive_mode(st) else self.run_parallel
            run_result = runner()
            if not run_result.get("ok"):
                return {
                    "ok": True,
                    "meeting": result.get("meeting"),
                    "warning": run_result.get("error", "无法启动讨论"),
                }
            result["task"] = run_result.get("task")
        return result

    def _normalize_guest_rows(self, rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]]]:
        invited: list[str] = []
        patches: dict[str, dict[str, Any]] = {}
        for row in rows:
            gid = str(row.get("id", "")).strip()
            if not gid:
                continue
            if row.get("invited"):
                invited.append(gid)
            patch = {
                k: row[k]
                for k in (
                    "role",
                    "role_id",
                    "model",
                    "command",
                    "executor_id",
                    "enabled",
                    "allow_parallel",
                    "timeout_seconds",
                )
                if k in row and row[k] is not None and row[k] != ""
            }
            if patch:
                patches[gid] = patch
        return invited, patches

    def _apply_guest_setup(
        self,
        meeting_dir: Path,
        *,
        invited: list[str],
        guest_patches: dict[str, dict[str, Any]],
        context_scope: str = "",
        owner_question: str = "",
    ) -> None:
        state = load_state(meeting_dir)
        if owner_question:
            state["next_question"] = owner_question
            state["owner_question"] = owner_question
        if invited:
            state["selected_guests"] = invited
        save_state(meeting_dir, state)
        save_overrides(
            meeting_dir,
            {
                "guests": guest_patches,
                "invited": invited,
                "setup": {"context_scope": context_scope},
            },
        )

    def start_meeting(
        self,
        *,
        topic: str,
        mode: str = "research",
        owner_question: str = "",
        context_scope: str = "",
        guest_rows: list[dict[str, Any]] | None = None,
        run_context_after: bool = False,
        invited_card_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            return {"ok": False, "error": "议题不能为空"}
        args = argparse.Namespace(
            topic=topic,
            question=owner_question.strip() or None,
            rounds_before_owner=3,
            mode=mode,
            max_rounds=None,
            stale_limit=5,
            scenario=None,
            bindings=None,
            bind=None,
        )
        try:
            with redirect_stdout(io.StringIO()):
                cmd_start(args)
        except SystemExit as exc:
            return {"ok": False, "error": str(exc) or "启动失败"}
        meeting_dir = self.try_current_meeting_dir()
        if meeting_dir is None:
            return {"ok": False, "error": "会议目录未创建"}
        if invited_card_ids:
            for cid in invited_card_ids:
                try:
                    self._invite_card_to_meeting(meeting_dir, cid)
                except ValueError:
                    pass
        elif guest_rows:
            invited, patches = self._normalize_guest_rows(guest_rows)
            if not invited:
                catalog = build_hosting_catalog()
                invited = list(catalog.get("default_invited", ["laguna", "codex"]))
            self._apply_guest_setup(
                meeting_dir,
                invited=invited,
                guest_patches=patches,
                context_scope=context_scope.strip(),
                owner_question=owner_question.strip() or topic,
            )
        elif not load_overrides(meeting_dir).get("invited"):
            catalog = build_hosting_catalog()
            for cid in catalog.get("default_invited", ["laguna", "codex"]):
                try:
                    self._invite_card_to_meeting(meeting_dir, cid)
                except ValueError:
                    pass
        scope = context_scope.strip()
        if run_context_after and scope:
            self._run_bg("context", lambda: cmd_context(argparse.Namespace(scope=scope)))
        return {"ok": True, "meeting": self.meeting_payload(meeting_dir)}

    def save_guest_config(
        self,
        *,
        guest_rows: list[dict[str, Any]],
        context_scope: str = "",
    ) -> dict[str, Any]:
        meeting_dir = self.try_current_meeting_dir()
        if meeting_dir is None:
            return {"ok": False, "error": "无活动会议"}
        invited, patches = self._normalize_guest_rows(guest_rows)
        if not invited:
            return {"ok": False, "error": "请至少邀请一位嘉宾"}
        self._apply_guest_setup(
            meeting_dir,
            invited=invited,
            guest_patches=patches,
            context_scope=context_scope.strip(),
        )
        return {"ok": True, "meeting": self.meeting_payload(meeting_dir)}

    def owner_ask(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            return {"ok": False, "error": "内容不能为空"}
        try:
            with redirect_stdout(io.StringIO()):
                cmd_ask(argparse.Namespace(text=text))
        except SystemExit as exc:
            return {"ok": False, "error": str(exc) or "更新失败"}
        return {"ok": True, "meeting": self.meeting_payload()}

    def owner_view(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            return {"ok": False, "error": "内容不能为空"}
        try:
            with redirect_stdout(io.StringIO()):
                cmd_view(argparse.Namespace(text=text))
        except SystemExit as exc:
            return {"ok": False, "error": str(exc) or "记录失败"}
        return {"ok": True, "meeting": self.meeting_payload()}

    def owner_continue(self) -> dict[str, Any]:
        try:
            with redirect_stdout(io.StringIO()):
                cmd_continue(argparse.Namespace())
        except SystemExit as exc:
            return {"ok": False, "error": str(exc) or "继续失败"}
        return {"ok": True, "meeting": self.meeting_payload()}

    def owner_stop(self) -> dict[str, Any]:
        try:
            with redirect_stdout(io.StringIO()):
                cmd_stop(argparse.Namespace())
        except SystemExit as exc:
            return {"ok": False, "error": str(exc) or "停止失败"}
        return {"ok": True, "meeting": self.meeting_payload()}

    def select_guests(self, guests: list[str]) -> dict[str, Any]:
        if not guests:
            return {"ok": False, "error": "请选择至少一位嘉宾"}
        try:
            with redirect_stdout(io.StringIO()):
                cmd_select(argparse.Namespace(guests=guests))
        except SystemExit as exc:
            return {"ok": False, "error": str(exc) or "选人失败"}
        return {"ok": True, "meeting": self.meeting_payload()}

    def run_context(self, scope: str) -> dict[str, Any]:
        scope = scope.strip()
        if not scope:
            return {"ok": False, "error": "范围不能为空"}
        return self._run_bg("context", lambda: cmd_context(argparse.Namespace(scope=scope)))

    def run_parallel(self) -> dict[str, Any]:
        return self._run_bg("run_parallel", lambda: cmd_run_parallel(argparse.Namespace()))

    def run_interactive(self) -> dict[str, Any]:
        return self._run_bg("run_interactive", lambda: cmd_run_interactive(argparse.Namespace()))