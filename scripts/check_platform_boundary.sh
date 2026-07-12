#!/usr/bin/env bash
# Enforce missionos platform boundary: no App imports under platform/missionos/
# or apps/platform_smoke/ (Phase 5 second consumer).
# Usage: ./scripts/check_platform_boundary.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# missionos core + minimal second-consumer fixture (must not import council).
SCAN_DIRS=(
  "$ROOT/platform/missionos"
  "$ROOT/apps/platform_smoke/platform_smoke"
)

# Patterns that must not appear in Platform / smoke Python sources.
FORBIDDEN='(from council|import council|from runtime_ext|import runtime_ext|from claim_lifecycle|import claim_lifecycle|from engine|import engine)'

_scan_dir() {
  local dir="$1"
  local label="$2"
  if [[ ! -d "$dir" ]]; then
    echo "ERROR: $label not found at $dir"
    exit 1
  fi
  if command -v rg >/dev/null 2>&1; then
    if rg -n "$FORBIDDEN" "$dir" --glob '*.py' 2>/dev/null; then
      echo ""
      echo "FAIL: forbidden App imports found under $label"
      exit 1
    fi
  else
    if grep -rEn "$FORBIDDEN" "$dir" --include='*.py' 2>/dev/null; then
      echo ""
      echo "FAIL: forbidden App imports found under $label"
      exit 1
    fi
  fi
}

for dir in "${SCAN_DIRS[@]}"; do
  _scan_dir "$dir" "${dir#"$ROOT"/}"
done

echo "platform boundary ok (missionos + platform_smoke)"