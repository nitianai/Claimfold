#!/usr/bin/env bash
# Run local Qoder CLI headless for Claimfold research guest.
# Prompt is read from stdin (engine invoke_cli). Prints final assistant message only.
set -euo pipefail

PROMPT="$(cat)"
if [[ -z "${PROMPT//[[:space:]]/}" ]]; then
  echo "# Qoder Error" >&2
  echo "Empty prompt on stdin" >&2
  exit 1
fi

if qodercli status 2>&1 | grep -qiE "not logged in|please run /login"; then
  echo "# Qoder Error" >&2
  echo "Not logged in. Run: NO_BROWSER=1 qodercli login" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

printf '%s' "$PROMPT" | qodercli -p \
  -w "$ROOT" \
  --permission-mode dont_ask \
  --tools default \
  -o text \
  2>/dev/null \
  | python3 "$(dirname "$0")/dedupe_guest_output.py"