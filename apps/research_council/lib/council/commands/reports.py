"""Council: commands/reports."""
from __future__ import annotations

import argparse
import json

from council.metrics import compute_metrics, metrics_markdown
from council.reports.generators import (
    generate_council_experiment_report,
    generate_council_investment_report,
)

from council.guests import load_guests
from council.state_store import get_current_meeting_dir, load_state


def cmd_report(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    metrics = compute_metrics(meeting_dir, state, load_guests())
    inv_path = meeting_dir / "investment_report.md"
    exp_path = meeting_dir / "council_experiment_report.md"
    inv_path.write_text(generate_council_investment_report(state, meeting_dir, metrics), encoding="utf-8")
    exp_path.write_text(generate_council_experiment_report(state, metrics), encoding="utf-8")
    print(f"Investment report: {inv_path}")
    print(f"Experiment report: {exp_path}")


def cmd_metrics(_: argparse.Namespace) -> None:
    meeting_dir = get_current_meeting_dir()
    state = load_state(meeting_dir)
    metrics = compute_metrics(meeting_dir, state, load_guests())

    md_path = meeting_dir / "metrics.md"
    json_path = meeting_dir / "metrics.json"
    md_path.write_text(metrics_markdown(metrics), encoding="utf-8")
    json_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(metrics_markdown(metrics))
    print(f"Saved: {md_path}")
    print(f"Saved: {json_path}")

