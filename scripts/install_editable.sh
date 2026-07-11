#!/usr/bin/env bash
# Editable install: missionos (platform) then research-council (app).
# Falls back to PYTHONPATH when pip is unavailable.
# Usage: ./scripts/install_editable.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_LIB="${ROOT}/apps/research_council/lib"
PLATFORM="${ROOT}/platform"

if python3 -m pip --version >/dev/null 2>&1; then
  echo "Installing missionos (platform)..."
  python3 -m pip install -e "${PLATFORM}"
  echo "Installing research-council (app)..."
  python3 -m pip install -e "${ROOT}/apps/research_council"
  python3 -c "import missionos; import engine; import council; print('editable install ok')"
else
  echo "pip unavailable; using PYTHONPATH fallback (${PLATFORM}:${APP_LIB})"
  export PYTHONPATH="${PLATFORM}:${APP_LIB}${PYTHONPATH:+:${PYTHONPATH}}"
  python3 -c "import missionos; import engine; import council; print('PYTHONPATH fallback ok')"
fi