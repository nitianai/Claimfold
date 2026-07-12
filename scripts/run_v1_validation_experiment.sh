#!/usr/bin/env bash
# v1 进化后对照实验（mock，可离线复现）
# 对照基线：docs/EXPERIMENTS.md 实验 B 基准（黄金 3 人单轮）+ 双轮语义闭环
# Usage: ./scripts/run_v1_validation_experiment.sh [--keep]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

KEEP=false
if [[ "${1:-}" == "--keep" ]]; then
  KEEP=true
fi

TMP="$(mktemp -d)"
export COUNCIL_DATA_ROOT="$TMP"
export COUNCIL_MOCK=1
export PYTHONPATH="${ROOT}/platform:${ROOT}/apps/research_council/lib${PYTHONPATH:+:${PYTHONPATH}}"

cleanup() {
  if $KEEP; then
    echo "data_root kept: $TMP"
  else
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

fail() { echo "VALIDATION FAIL: $*" >&2; exit 1; }

echo "=== v1 Validation Experiment (mock) ===" >&2
echo "data_root: $TMP" >&2
echo "baseline reference: EXPERIMENTS.md §2 黄金-3人 + 双轮语义闭环" >&2
echo "" >&2

./council.sh init >/dev/null 2>&1
./council.sh start "未来一周黄金走势（v1 对照）" --mode research \
  --failure-policy allow_partial --require-before-promote >/dev/null 2>&1
./council.sh context "黄金、美元、美债、地缘政治" >/dev/null 2>&1

# 3 职能位（对齐实验 B 基准人数；guest 名随本地 config 解析）
./council.sh select qwen nemo codex >/dev/null 2>&1 || ./council.sh select codex qoder laguna >/dev/null 2>&1

MEETING_ID="$(tr -d '\n' < "$TMP/.current_meeting")"
MEETING_DIR="$TMP/meetings/$MEETING_ID"
[[ -d "$MEETING_DIR" ]] || fail "meeting dir missing"

./council.sh run-parallel >/dev/null 2>&1
./council.sh run-parallel >/dev/null 2>&1
./council.sh metrics >/dev/null 2>&1

REPORT_JSON="$MEETING_DIR/v1_validation_report.json"
VALIDATION_ROOT="$ROOT" python3 - "$MEETING_DIR" "$MEETING_ID" "$REPORT_JSON" <<'PY'
import json
import os
import sys
from pathlib import Path

meeting_dir = Path(sys.argv[1])
meeting_id = sys.argv[2]
report_path = Path(sys.argv[3])
root = Path(os.environ["VALIDATION_ROOT"])

sys.path.insert(0, str(root / "apps" / "research_council" / "lib"))
from council.verify import verify_research_semantic_loop  # noqa: E402
from meeting_quality import analyze_meeting  # noqa: E402

state_path = meeting_dir / "meeting_state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
metrics = json.loads((meeting_dir / "metrics.json").read_text(encoding="utf-8"))
analysis = analyze_meeting(meeting_dir)

ok_loop, loop_errors = verify_research_semantic_loop(meeting_dir, round_num=2)
errors: list[str] = []

if state.get("round", 0) < 2:
    errors.append(f"expected round>=2, got {state.get('round')}")
if not ok_loop:
    errors.extend(f"semantic_loop: {e}" for e in loop_errors)
if metrics.get("guest_failure_rate_pct", 100) != 0:
    errors.append(f"guest_failure_rate_pct={metrics.get('guest_failure_rate_pct')}")
if metrics.get("summary_json_parse_success_rate", 0) != 100:
    errors.append(
        f"summary_json_parse_success_rate={metrics.get('summary_json_parse_success_rate')}"
    )
if len(state.get("confirmed_points", [])) == 0:
    errors.append("confirmed_points empty after 2 rounds")
if not state.get("guest_slots"):
    errors.append("guest_slots missing")
if not (meeting_dir / "events.jsonl").is_file():
    errors.append("events.jsonl missing")

report = {
    "experiment": "v1_validation_mock",
    "meeting_id": meeting_id,
    "topic": state.get("topic"),
    "rounds": state.get("round"),
    "confirmed_points": len(state.get("confirmed_points", [])),
    "conflicts": len(state.get("conflicts", [])),
    "open_questions": len(state.get("open_questions", [])),
    "guest_turns": analysis.get("guest_turns"),
    "mock_guest_rate": analysis.get("mock_guest_rate"),
    "guest_failure_rate_pct": metrics.get("guest_failure_rate_pct"),
    "summary_json_parse_success_rate": metrics.get("summary_json_parse_success_rate"),
    "semantic_loop_ok": ok_loop,
    "guest_slots": len(state.get("guest_slots", {})),
    "failure_policy": state.get("failure_policy"),
    "require_before_promote": (state.get("hitl") or {}).get("require_before_promote"),
    "baseline_ref": "meet-20260710-021348 (3 guests, real CLI)",
    "verdict": "PASS" if not errors else "FAIL",
    "errors": errors,
}

report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if errors:
    sys.exit(1)
PY

cat "$REPORT_JSON"
echo ""
echo "=== v1 Validation PASSED ($MEETING_ID) ===" >&2
echo "report: $REPORT_JSON" >&2