#!/usr/bin/env bash
# Run Grok Build headless for Claimfold research guest (laguna / grok alias).
# Prompt is read from stdin (engine invoke_cli). Prints final assistant message only.
set -euo pipefail

PROMPT="$(cat)"
if [[ -z "${PROMPT//[[:space:]]/}" ]]; then
  echo "# Grok Error" >&2
  echo "Empty prompt on stdin" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${GROK_GUEST_MODEL:-hermes-grok/grok-4.3}"
GROK_BIN="${GROK_BIN:-grok}"

# Research guest: context-only reply, no tool side effects.
"$GROK_BIN" -p "$PROMPT" \
  -m "$MODEL" \
  --cwd "$ROOT" \
  --always-approve \
  --output-format plain \
  --max-turns 1 \
  --disallowed-tools 'run_terminal_cmd,read_file,grep,list_dir,web_search,web_fetch,search_replace,todo_write,task,Agent' \
  2>/dev/null \
  | python3 "$(dirname "$0")/dedupe_guest_output.py"