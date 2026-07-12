#!/usr/bin/env bash
# Local CI gate (P2) — run before push or via git hook.
# Usage: ./scripts/ci.sh [--quick]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
unset COUNCIL_DATA_ROOT

QUICK=false
if [[ "${1:-}" == "--quick" ]]; then
  QUICK=true
fi

echo "=== Claimfold CI ==="
echo "root: $ROOT"
echo "python: $(python3 --version 2>&1)"
echo ""

echo "[0/7] Editable install (missionos + research-council)"
./scripts/install_editable.sh
if ! python3 -m pip --version >/dev/null 2>&1; then
  export PYTHONPATH="${ROOT}/platform:${ROOT}/apps/research_council/lib${PYTHONPATH:+:${PYTHONPATH}}"
fi

echo ""
echo "[1/7] Platform boundary + tests (tests/platform/)"
./scripts/check_platform_boundary.sh
python3 tests/platform/run_tests.py

echo ""
echo "[2/7] App tests (tests/app/run_tests.py)"
python3 tests/app/run_tests.py

echo ""
echo "[3/7] Engine import smoke"
python3 -c "import missionos; import engine; print('engine import ok')"

if ! $QUICK; then
  echo ""
  echo "[4/7] Strict default (fail-closed)"
  python3 -c "
from missionos.utils import set_relax_cli, strict_cli_enabled
set_relax_cli(False)
assert strict_cli_enabled(), 'strict must default on'
print('strict default ok')
"
  echo ""
  echo "[5/7] Meeting E2E (mock offline, auto-stop on exit)"
  export COUNCIL_AUTO_STOP=1
  ./scripts/test_meeting_e2e.sh
  ./scripts/test_interactive_meeting.sh
  echo ""
  echo "[6/7] v1 validation experiment (mock gold, 2 rounds)"
  ./scripts/run_v1_validation_experiment.sh
else
  echo ""
  echo "[4/7] Skipped strict (--quick)"
  echo "[5/7] Skipped meeting e2e (--quick)"
  echo "[6/7] Skipped v1 validation (--quick)"
fi

echo ""
echo "=== CI PASSED ==="