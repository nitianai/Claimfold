#!/usr/bin/env bash
# Smoke-test interactive meeting flow (mock guests). Exit non-zero on failure.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="${TMPDIR:-/tmp}/council-interactive-$$"
export COUNCIL_DATA_ROOT="$TMP"
export COUNCIL_MOCK=1
export COUNCIL_AUTO_STOP=1

# shellcheck source=meeting_test_guard.sh
source "$ROOT/scripts/meeting_test_guard.sh"

_teardown() {
  local rc=$?
  meeting_test_guard_stop
  rm -rf "$TMP"
  exit "$rc"
}
trap _teardown EXIT

cd "$ROOT"
./council.sh start "交互验收" --mode interactive >/dev/null
./council.sh select codex qoder >/dev/null
./council.sh floor request qoder --urgency 5 --build-on msg-placeholder 2>/dev/null || true

# Step mode: first guest only
./council.sh session step >/dev/null
MEET_DIR=$(ls -d "$TMP"/meetings/meet-* | head -1)
STATE="$MEET_DIR/meeting_state.json"
test -f "$STATE"
STATUS=$(python3 -c "import json; print(json.load(open('$STATE'))['session_status'])")
test "$STATUS" = "paused"

# Resume to completion
./council.sh session resume >/dev/null
ROUND=$(python3 -c "import json; print(json.load(open('$STATE'))['round'])")
test "$ROUND" = "1"

EVENTS="$MEET_DIR/events.jsonl"
python3 -c "
import json
lines = open('$EVENTS').read().splitlines()
types = [json.loads(l)['event'] for l in lines if l.strip()]
need = ['session_started','floor_granted','message_committed','floor_yielded','session_ended']
for n in need:
    assert n in types, f'missing event {n}'
print('events ok:', len(types))
"

./council.sh session inspect --annotations >/dev/null
./council.sh session replay --tail 5 >/dev/null

meeting_test_guard_stop
test -f "$MEET_DIR/final.md" || { echo "FAIL: missing final.md" >&2; exit 1; }

echo "interactive meeting smoke ok ($TMP)"