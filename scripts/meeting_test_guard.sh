#!/usr/bin/env bash
# Auto-stop the active council meeting when a test/verification script exits.
# Usage:
#   source scripts/meeting_test_guard.sh
#   meeting_test_guard_enable          # trap EXIT → auto stop
#   meeting_test_guard_stop            # or call explicitly

meeting_test_guard_stop() {
  case "${COUNCIL_AUTO_STOP:-1}" in
    0|false|FALSE|no|NO) return 0 ;;
  esac
  if [[ -z "${ROOT:-}" ]]; then
    return 0
  fi
  local data_root="${COUNCIL_DATA_ROOT:-$ROOT}"
  local ptr="$data_root/.current_meeting"
  if [[ ! -f "$ptr" ]]; then
    return 0
  fi
  local meeting_id
  meeting_id="$(tr -d '[:space:]' < "$ptr")"
  if [[ -z "$meeting_id" ]]; then
    return 0
  fi
  local state_file="$data_root/meetings/$meeting_id/meeting_state.json"
  if [[ -f "$state_file" ]]; then
    local status
    status="$(python3 -c "import json; print(json.load(open('$state_file')).get('status',''))" 2>/dev/null || true)"
    if [[ "$status" == "stopped" ]]; then
      return 0
    fi
  fi
  (cd "$ROOT" && ./council.sh stop >/dev/null 2>&1) || true
}

_meeting_test_guard_teardown() {
  local rc=$?
  meeting_test_guard_stop
  return "$rc"
}

meeting_test_guard_enable() {
  trap '_meeting_test_guard_teardown' EXIT
}