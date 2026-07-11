#!/usr/bin/env bash
# Claimfold Council Web UI — chat-room view
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$ROOT/apps/research_council"
export PYTHONPATH="${ROOT}/platform:${APP_DIR}/lib${PYTHONPATH:+:${PYTHONPATH}}"

HOST="${COUNCIL_WEB_HOST:-127.0.0.1}"
PORT="${COUNCIL_WEB_PORT:-8787}"

exec python3 "$APP_DIR/web/server.py" --host "$HOST" --port "$PORT" "$@"