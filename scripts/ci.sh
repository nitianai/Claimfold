#!/usr/bin/env bash
# Local CI gate (P2) — run before push or via git hook.
# Usage: ./scripts/ci.sh [--quick]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

QUICK=false
if [[ "${1:-}" == "--quick" ]]; then
  QUICK=true
fi

echo "=== Claimfold CI ==="
echo "root: $ROOT"
echo "python: $(python3 --version 2>&1)"
echo ""

echo "[1/3] Regression tests (run_tests.py)"
python3 tests/run_tests.py

echo ""
echo "[2/3] Engine import smoke"
python3 -c "import sys; sys.path.insert(0,'lib'); import engine; print('engine import ok')"

if ! $QUICK; then
  echo ""
  echo "[3/3] Strict default (fail-closed)"
  python3 -c "
import sys
sys.path.insert(0,'lib')
from utils import set_relax_cli, strict_cli_enabled
set_relax_cli(False)
assert strict_cli_enabled(), 'strict must default on'
print('strict default ok')
"
else
  echo ""
  echo "[3/3] Skipped (--quick)"
fi

echo ""
echo "=== CI PASSED ==="