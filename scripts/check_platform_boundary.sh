#!/usr/bin/env bash
# Enforce missionos platform boundary: no App imports under platform/missionos/.
# Usage: ./scripts/check_platform_boundary.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM_DIR="$ROOT/platform/missionos"

if [[ ! -d "$PLATFORM_DIR" ]]; then
  echo "ERROR: platform/missionos/ not found at $PLATFORM_DIR"
  exit 1
fi

# Patterns that must not appear in Platform Python sources.
FORBIDDEN='(from council|import council|from runtime_ext|import runtime_ext|from claim_lifecycle|import claim_lifecycle|from engine|import engine)'

if command -v rg >/dev/null 2>&1; then
  if rg -n "$FORBIDDEN" "$PLATFORM_DIR" --glob '*.py' 2>/dev/null; then
    echo ""
    echo "FAIL: forbidden App imports found under platform/missionos/"
    exit 1
  fi
else
  if grep -rEn "$FORBIDDEN" "$PLATFORM_DIR" --include='*.py' 2>/dev/null; then
    echo ""
    echo "FAIL: forbidden App imports found under platform/missionos/"
    exit 1
  fi
fi

echo "platform boundary ok ($PLATFORM_DIR)"