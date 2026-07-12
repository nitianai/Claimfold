#!/usr/bin/env bash
# 真实 CLI 黄金复验（v1 进化后 floor 对照）
# 基线参照：docs/EXPERIMENTS.md §2 meet-20260710-021348（3 人单轮）
#           §1 meet-20260710-015200（2 轮语义闭环）
# Usage:
#   ./scripts/run_gold_revalidation_cli.sh
#   ./scripts/run_gold_revalidation_cli.sh --baseline meet-20260710-015200
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

unset COUNCIL_MOCK
export COUNCIL_DATA_ROOT="$ROOT"
export PYTHONPATH="${ROOT}/platform:${ROOT}/apps/research_council/lib${PYTHONPATH:+:${PYTHONPATH}}"

BASELINE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --baseline) BASELINE="${2:-}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$BASELINE" ]]; then
  if [[ -d "$ROOT/meetings/meet-20260710-021348" ]]; then
    BASELINE="meet-20260710-021348"
  elif [[ -d "$ROOT/meetings/meet-20260710-015200" ]]; then
    BASELINE="meet-20260710-015200"
  fi
fi

fail() { echo "REVALIDATION FAIL: $*" >&2; exit 1; }

echo "=== Gold CLI Revalidation (v1) ===" >&2
echo "data_root: $ROOT" >&2
echo "baseline: ${BASELINE:-none}" >&2
echo "guests: nemo + gptoss20 + north (3 职能位，对齐 §2 人数)" >&2
echo "" >&2

./council.sh init >/dev/null 2>&1 || true
./council.sh start "未来一周黄金走势（v1 真实 CLI 复验）" --mode research \
  --failure-policy allow_partial >/dev/null 2>&1

MEETING_ID="$(tr -d '\n' < "$COUNCIL_DATA_ROOT/.current_meeting")"
MEETING_DIR="$COUNCIL_DATA_ROOT/meetings/$MEETING_ID"
[[ -d "$MEETING_DIR" ]] || fail "meeting dir missing: $MEETING_DIR"

echo "[1/5] context …" >&2
./council.sh context "黄金、美元、美债、地缘政治" 2>&1 | tail -3 >&2

echo "[2/5] select nemo gptoss20 north …" >&2
./council.sh select nemo gptoss20 north >/dev/null 2>&1

echo "[3/5] run-parallel round 1 …" >&2
./council.sh run-parallel 2>&1 | tail -8 >&2

echo "[4/5] run-parallel round 2 …" >&2
./council.sh run-parallel 2>&1 | tail -10 >&2

./council.sh metrics >/dev/null 2>&1

REPORT_JSON="$MEETING_DIR/gold_revalidation_report.json"
VALIDATION_ROOT="$COUNCIL_DATA_ROOT" BASELINE_ID="$BASELINE" python3 - "$MEETING_DIR" "$MEETING_ID" "$REPORT_JSON" <<'PY'
import json
import os
import sys
from pathlib import Path

meeting_dir = Path(sys.argv[1])
meeting_id = sys.argv[2]
report_path = Path(sys.argv[3])
root = Path(os.environ["VALIDATION_ROOT"])
baseline_id = os.environ.get("BASELINE_ID", "").strip()

sys.path.insert(0, str(root / "apps" / "research_council" / "lib"))
from council.verify import verify_research_semantic_loop  # noqa: E402
from meeting_quality import analyze_meeting  # noqa: E402

state = json.loads((meeting_dir / "meeting_state.json").read_text(encoding="utf-8"))
metrics = json.loads((meeting_dir / "metrics.json").read_text(encoding="utf-8"))
analysis = analyze_meeting(meeting_dir)
ok_loop, loop_errors = verify_research_semantic_loop(meeting_dir, round_num=2)

errors: list[str] = []
if state.get("round", 0) < 2:
    errors.append(f"round<2 ({state.get('round')})")
if not ok_loop:
    errors.extend(loop_errors)
if metrics.get("guest_failure_rate_pct", 100) > 0:
    errors.append(f"guest_failure_rate_pct={metrics.get('guest_failure_rate_pct')}")
if metrics.get("summary_json_parse_success_rate", 0) < 100:
    errors.append(f"json_parse={metrics.get('summary_json_parse_success_rate')}")
if analysis.get("mock_guest_rate", 1) > 0.35:
    errors.append(f"mock_guest_rate={analysis.get('mock_guest_rate')} (>35% 阈值)")

baseline_summary = None
if baseline_id:
    bdir = root / "meetings" / baseline_id
    if bdir.is_dir():
        bstate = json.loads((bdir / "meeting_state.json").read_text(encoding="utf-8"))
        bmetrics_path = bdir / "metrics.json"
        bmetrics = (
            json.loads(bmetrics_path.read_text(encoding="utf-8"))
            if bmetrics_path.is_file()
            else {}
        )
        baseline_summary = {
            "meeting_id": baseline_id,
            "rounds": bstate.get("round"),
            "cp": len(bstate.get("confirmed_points", [])),
            "cf": len(bstate.get("conflicts", [])),
            "oq": len(bstate.get("open_questions", [])),
            "guest_failure_rate_pct": bmetrics.get("guest_failure_rate_pct"),
            "mock_guest_rate_pct": bmetrics.get("mock_guest_rate_pct"),
        }

report = {
    "experiment": "gold_revalidation_cli_v1",
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
    "avg_round_duration_s": metrics.get("avg_round_duration_s"),
    "semantic_loop_ok": ok_loop,
    "guest_slots": len(state.get("guest_slots", {})),
    "baseline": baseline_summary,
    "verdict": "PASS" if not errors else "FAIL",
    "errors": errors,
}
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
if errors:
    sys.exit(1)
PY

echo "" >&2
echo "=== Gold CLI Revalidation PASSED ($MEETING_ID) ===" >&2
echo "report: $REPORT_JSON" >&2
if [[ -n "$BASELINE" ]]; then
  COUNCIL_DATA_ROOT="$COUNCIL_DATA_ROOT" python3 "$ROOT/apps/research_council/scripts/compare_meetings.py" "$MEETING_ID" "$BASELINE" 2>&1 | tail -20 >&2 || true
fi