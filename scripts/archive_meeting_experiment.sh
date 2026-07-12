#!/usr/bin/env bash
# 实验会议归档：刷新 metrics + 分析摘要 + 可选基线对比
# Usage:
#   ./scripts/archive_meeting_experiment.sh
#   ./scripts/archive_meeting_experiment.sh meet-20260712-145503
#   ./scripts/archive_meeting_experiment.sh meet-20260712-145503 --baseline meet-20260710-015200
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export COUNCIL_DATA_ROOT="${COUNCIL_DATA_ROOT:-$ROOT}"
export PYTHONPATH="${ROOT}/platform:${ROOT}/apps/research_council/lib${PYTHONPATH:+:${PYTHONPATH}}"

exec python3 "${ROOT}/apps/research_council/scripts/archive_meeting_experiment.py" "$@"