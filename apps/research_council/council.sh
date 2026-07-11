#!/usr/bin/env bash
# Council Engine V0.1 — deterministic multi-model meeting workflow runtime.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${APP_DIR}/../.." && pwd)"
export PYTHONPATH="${REPO_DIR}/platform:${APP_DIR}/lib${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 "${APP_DIR}/lib/engine.py" "$@"