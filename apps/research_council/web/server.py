#!/usr/bin/env python3
"""Claimfold Council Web UI — chat-room view over meeting artifacts."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = APP_DIR.parent.parent
sys.path.insert(0, str(REPO_DIR / "platform"))
sys.path.insert(0, str(APP_DIR / "lib"))

from council.web.service import CouncilWebService  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
SERVICE = CouncilWebService()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


class CouncilHandler(BaseHTTPRequestHandler):
    server_version = "ClaimfoldCouncil/0.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api_get(parsed)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        self._handle_api_post(parsed)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/project/config":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        try:
            data = _read_json(self)
        except json.JSONDecodeError:
            _json_response(self, 400, {"ok": False, "error": "invalid json"})
            return
        result = SERVICE.save_project_config(list(data.get("guest_rows") or []))
        status = 200 if result.get("ok", True) else 400
        _json_response(self, status, result)

    def _handle_api_get(self, parsed) -> None:
        path = parsed.path
        if path == "/api/health":
            _json_response(self, 200, {"ok": True})
            return
        if path == "/api/meeting/current":
            _json_response(self, 200, SERVICE.meeting_payload())
            return
        if path == "/api/meetings":
            _json_response(self, 200, {"meetings": SERVICE.list_meetings()})
            return
        if path == "/api/guests":
            meeting = SERVICE.meeting_payload()
            _json_response(self, 200, {"guests": meeting.get("guests", [])})
            return
        if path == "/api/tasks/status":
            _json_response(self, 200, SERVICE.task_status())
            return
        if path == "/api/hosting/catalog":
            _json_response(self, 200, SERVICE.hosting_catalog())
            return
        if path == "/api/project/config":
            _json_response(self, 200, SERVICE.project_config_payload())
            return
        if path == "/api/role-cards":
            _json_response(self, 200, SERVICE.role_cards_payload())
            return
        _json_response(self, 404, {"ok": False, "error": "not found"})

    def _handle_api_post(self, parsed) -> None:
        path = parsed.path
        try:
            data = _read_json(self)
        except json.JSONDecodeError:
            _json_response(self, 400, {"ok": False, "error": "invalid json"})
            return

        routes = {
            "/api/meeting/start": lambda: SERVICE.start_meeting(
                topic=str(data.get("topic", "")),
                mode=str(data.get("mode", "research")),
                owner_question=str(data.get("owner_question", "")),
                context_scope=str(data.get("context_scope", "")),
                guest_rows=list(data.get("guest_rows") or []),
                run_context_after=bool(data.get("run_context_after", False)),
                invited_card_ids=list(data.get("invited_card_ids") or []),
            ),
            "/api/role-cards/save": lambda: SERVICE.save_role_card(
                data.get("card") or data,
                card_id=str(data.get("id", "")),
            ),
            "/api/role-cards/delete": lambda: SERVICE.remove_role_card(str(data.get("id", ""))),
            "/api/meeting/invite": lambda: SERVICE.invite_role_card(str(data.get("card_id", ""))),
            "/api/meeting/uninvite": lambda: SERVICE.uninvite_role_card(str(data.get("card_id", ""))),
            "/api/meeting/guest-config": lambda: SERVICE.save_guest_config(
                guest_rows=list(data.get("guest_rows") or []),
                context_scope=str(data.get("context_scope", "")),
            ),
            "/api/meeting/switch": lambda: SERVICE.switch_meeting(str(data.get("meeting_id", ""))),
            "/api/owner/ask": lambda: SERVICE.owner_ask(str(data.get("text", ""))),
            "/api/owner/view": lambda: SERVICE.owner_view(str(data.get("text", ""))),
            "/api/owner/continue": lambda: SERVICE.owner_continue(),
            "/api/owner/stop": lambda: SERVICE.owner_stop(),
            "/api/select": lambda: SERVICE.select_guests(list(data.get("guests") or [])),
            "/api/context": lambda: SERVICE.run_context(str(data.get("scope", ""))),
            "/api/run-parallel": lambda: SERVICE.run_parallel(),
            "/api/run-interactive": lambda: SERVICE.run_interactive(),
            "/api/meeting/speak": lambda: SERVICE.meeting_speak(
                mode=str(data.get("mode", "ask")),
                text=str(data.get("text", "")),
                run_next=bool(data.get("run_next", False)),
            ),
        }
        if path not in routes:
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return
        result = routes[path]()
        status = 200 if result.get("ok", True) else 400
        _json_response(self, status, result)

    def _serve_static(self, req_path: str) -> None:
        if req_path in ("/", ""):
            file_path = STATIC_DIR / "index.html"
        else:
            rel = req_path.lstrip("/")
            if ".." in rel:
                self.send_error(403)
                return
            file_path = STATIC_DIR / rel
        if not file_path.is_file():
            self.send_error(404)
            return
        content = file_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Claimfold Council Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    if not STATIC_DIR.is_dir():
        raise SystemExit(f"static dir missing: {STATIC_DIR}")

    httpd = ThreadingHTTPServer((args.host, args.port), CouncilHandler)
    print(f"Council Web UI: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()