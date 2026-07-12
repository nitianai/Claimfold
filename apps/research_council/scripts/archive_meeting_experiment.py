#!/usr/bin/env python3
"""Archive meeting experiment artifacts: metrics, analysis, optional baseline compare."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = APP_ROOT.parent.parent
_data_root = os.environ.get("COUNCIL_DATA_ROOT", "").strip()
DATA_ROOT = Path(_data_root).resolve() if _data_root else REPO_ROOT
MEETINGS_DIR = DATA_ROOT / "meetings"
CURRENT_MEETING_FILE = DATA_ROOT / ".current_meeting"

sys.path.insert(0, str(APP_ROOT / "lib"))

from council.guests import load_guests  # noqa: E402
from council.metrics import compute_metrics, metrics_markdown  # noqa: E402
from council.state_store import load_state  # noqa: E402
from council.verify import verify_research_semantic_loop  # noqa: E402
from meeting_quality import analyze_meeting, compare_reports  # noqa: E402


def resolve_meeting(path_or_id: str) -> Path:
    p = Path(path_or_id)
    if p.is_dir():
        return p.resolve()
    candidate = MEETINGS_DIR / path_or_id
    if candidate.is_dir():
        return candidate.resolve()
    if not path_or_id.startswith("meet-"):
        candidate = MEETINGS_DIR / f"meet-{path_or_id}"
        if candidate.is_dir():
            return candidate.resolve()
    raise FileNotFoundError(path_or_id)


def read_current_meeting_id() -> str:
    if not CURRENT_MEETING_FILE.is_file():
        raise FileNotFoundError(f"no .current_meeting at {CURRENT_MEETING_FILE}")
    meeting_id = CURRENT_MEETING_FILE.read_text(encoding="utf-8").strip()
    if not meeting_id:
        raise FileNotFoundError("empty .current_meeting pointer")
    return meeting_id


def refresh_metrics(meeting_dir: Path) -> dict:
    state = load_state(meeting_dir)
    guests = load_guests()
    metrics = compute_metrics(meeting_dir, state, guests)
    (meeting_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (meeting_dir / "metrics.md").write_text(metrics_markdown(metrics) + "\n", encoding="utf-8")
    return metrics


def semantic_loop_status(meeting_dir: Path, state: dict) -> dict:
    mode = str(state.get("meeting_mode") or state.get("output_format") or "")
    round_num = int(state.get("round") or 0)
    if mode != "research" or round_num < 2:
        return {"checked": False, "ok": None, "round": round_num, "errors": []}
    ok, errors = verify_research_semantic_loop(meeting_dir, round_num=2)
    return {"checked": True, "ok": ok, "round": round_num, "errors": list(errors)}


def build_archive_report(
    meeting_dir: Path,
    *,
    baseline_id: str = "",
    refresh: bool = True,
) -> dict:
    state = load_state(meeting_dir)
    meeting_id = str(state.get("meeting_id") or meeting_dir.name)

    metrics = refresh_metrics(meeting_dir) if refresh else {}
    metrics_path = meeting_dir / "metrics.json"
    if not refresh and metrics_path.is_file():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    elif not metrics and metrics_path.is_file():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    analysis = analyze_meeting(meeting_dir)
    loop = semantic_loop_status(meeting_dir, state)

    artifacts: dict[str, str] = {
        "meeting_state_json": "meeting_state.json",
        "metrics_json": "metrics.json",
        "metrics_md": "metrics.md",
        "experiment_archive_json": "experiment_archive.json",
    }
    for name in ("events.jsonl", "final.md", "gold_revalidation_report.json", "v1_validation_report.json"):
        if (meeting_dir / name).is_file():
            artifacts[name.replace(".", "_")] = name

    comparison_path = meeting_dir / "quality_comparison.md"
    baseline_summary = None
    if baseline_id:
        baseline_dir = resolve_meeting(baseline_id)
        comparison_md = compare_reports(meeting_dir, baseline_dir)
        comparison_path.write_text(comparison_md + "\n", encoding="utf-8")
        artifacts["quality_comparison_md"] = "quality_comparison.md"
        bstate = load_state(baseline_dir)
        baseline_summary = {
            "meeting_id": baseline_dir.name,
            "topic": bstate.get("topic"),
            "rounds": bstate.get("round"),
            "cp": len(bstate.get("confirmed_points", [])),
            "cf": len(bstate.get("conflicts", [])),
            "oq": len(bstate.get("open_questions", [])),
        }

    return {
        "experiment": "meeting_experiment_archive",
        "meeting_id": meeting_id,
        "topic": state.get("topic"),
        "meeting_mode": state.get("meeting_mode") or state.get("output_format"),
        "archived_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_root": str(DATA_ROOT),
        "rounds": state.get("round"),
        "confirmed_points": len(state.get("confirmed_points", [])),
        "conflicts": len(state.get("conflicts", [])),
        "open_questions": len(state.get("open_questions", [])),
        "analysis": analysis,
        "metrics": metrics,
        "semantic_loop": loop,
        "baseline": baseline_summary,
        "artifacts": artifacts,
        "verdict": "ARCHIVED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive Claimfold meeting experiment outputs")
    parser.add_argument(
        "meeting_id",
        nargs="?",
        default="",
        help="Meeting id or path (default: .current_meeting)",
    )
    parser.add_argument("--baseline", default="", help="Baseline meeting id for quality_comparison.md")
    parser.add_argument(
        "--no-refresh-metrics",
        action="store_true",
        help="Skip recomputing metrics.json / metrics.md",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Override experiment_archive.json path (default: <meeting>/experiment_archive.json)",
    )
    args = parser.parse_args()

    meeting_ref = args.meeting_id.strip() or read_current_meeting_id()
    try:
        meeting_dir = resolve_meeting(meeting_ref)
    except FileNotFoundError:
        print(json.dumps({"error": f"meeting not found: {meeting_ref}"}, indent=2), file=sys.stderr)
        return 2

    report = build_archive_report(
        meeting_dir,
        baseline_id=args.baseline.strip(),
        refresh=not args.no_refresh_metrics,
    )
    out_path = Path(args.output) if args.output else meeting_dir / "experiment_archive.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nArchive written: {out_path}", file=sys.stderr)
    if args.baseline.strip():
        print(f"Comparison: {meeting_dir / 'quality_comparison.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())