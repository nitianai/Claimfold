#!/usr/bin/env bash
# Run local Codex headless (codex exec) for Claimfold Data Guest / reasoning guest.
# Prompt is read from stdin (engine invoke_cli). Prints final assistant message only.
set -euo pipefail

OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

PROMPT="$(cat)"
if [[ -z "${PROMPT//[[:space:]]/}" ]]; then
  echo "# Codex Error" >&2
  echo "Empty prompt on stdin" >&2
  exit 1
fi

printf '%s' "$PROMPT" | codex exec \
  --skip-git-repo-check \
  --sandbox read-only \
  --ephemeral \
  -o "$OUT" \
  - 2>/dev/null

if [[ -s "$OUT" ]]; then
  python3 "$(dirname "$0")/dedupe_guest_output.py" < "$OUT"
  exit 0
fi

# Fallback: parse stdout tail if -o empty
printf '%s' "$PROMPT" | codex exec --skip-git-repo-check --sandbox read-only --ephemeral - 2>/dev/null \
  | awk '/^codex$/{p=1;next} p&&NF{line=$0} END{print line}'