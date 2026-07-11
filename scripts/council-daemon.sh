#!/usr/bin/env bash
# Council session daemon — health check and state watch.
# Usage: ./scripts/council-daemon.sh check|watch|daily [--interval N]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="${ROOT}/apps/research_council"
export PYTHONPATH="${ROOT}/platform:${APP_DIR}/lib${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 "${APP_DIR}/scripts/council_daemon.py" "$@"