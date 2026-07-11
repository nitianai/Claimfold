#!/usr/bin/env bash
# Offline mock meeting e2e — validates core council workflow after each change.
# Usage: ./scripts/test_meeting_e2e.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TMP="$(mktemp -d)"
export COUNCIL_DATA_ROOT="$TMP"
export COUNCIL_MOCK=1
export COUNCIL_AUTO_STOP=1

# shellcheck source=meeting_test_guard.sh
source "$ROOT/scripts/meeting_test_guard.sh"
meeting_test_guard_enable

trap 'rm -rf "$TMP"; unset COUNCIL_DATA_ROOT' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

echo "=== Meeting E2E (mock) ==="
echo "data_root: $TMP"

./council.sh init >/dev/null
./council.sh start "E2E 冒烟测试" --mode research >/dev/null

MEETING_ID="$(cat "$TMP/.current_meeting")"
MEETING_DIR="$TMP/meetings/$MEETING_ID"
[[ -d "$MEETING_DIR" ]] || fail "meeting dir missing: $MEETING_DIR"

./council.sh context "黄金、美元、美债" >/dev/null
[[ -f "$MEETING_DIR/context/market_context.md" ]] || fail "missing market_context.md"
[[ -f "$MEETING_DIR/context/manifest.json" ]] || fail "missing manifest.json"
[[ -f "$MEETING_DIR/context/market_context.json" ]] || fail "missing market_context.json"

./council.sh select codex qoder >/dev/null
./council.sh run-parallel >/dev/null
[[ -f "$MEETING_DIR/meeting_state.json" ]] || fail "missing meeting_state.json"

ROUND_RAW_COUNT="$(find "$MEETING_DIR/raw" -name 'round-001-*.md' 2>/dev/null | wc -l)"
[[ "$ROUND_RAW_COUNT" -ge 2 ]] || fail "expected >=2 raw outputs, got $ROUND_RAW_COUNT"

./council.sh metrics >/dev/null
[[ -f "$MEETING_DIR/metrics.json" ]] || fail "missing metrics.json"

./council.sh report >/dev/null
[[ -f "$MEETING_DIR/investment_report.md" ]] || fail "missing investment_report.md"

./council.sh status >/dev/null

./scripts/council-daemon.sh check >/dev/null || fail "daemon check failed during active meeting"

# Explicit stop (guard also stops on EXIT if this line is skipped)
./council.sh stop >/dev/null
[[ -f "$MEETING_DIR/final.md" ]] || fail "missing final.md"
python3 -c "import json; s=json.load(open('$MEETING_DIR/meeting_state.json')); assert s.get('status')=='stopped'"

echo "=== Meeting E2E PASSED ($MEETING_ID) ==="