"""Text formatting and artifact path helpers."""
from __future__ import annotations

from pathlib import Path

from missionos.formatting import format_list, render_template, round_tag

__all__ = [
    "artifact_paths",
    "format_guest_summaries",
    "format_list",
    "render_template",
    "round_tag",
]


def format_guest_summaries(summaries: dict[str, str]) -> str:
    if not summaries:
        return "(无)"
    lines = []
    for guest, summary in summaries.items():
        lines.append(f"### {guest}")
        lines.append(summary.strip() or "(空)")
    return "\n".join(lines)


def artifact_paths(meeting_dir: Path, round_num: int, guest: str, *, json_mode: bool = True) -> dict[str, Path]:
    tag = round_tag(round_num)
    paths = {
        "prompt": meeting_dir / "prompts" / f"round-{tag}-{guest}.prompt.md",
        "raw": meeting_dir / "raw" / f"round-{tag}-{guest}.{'json' if json_mode else 'md'}",
    }
    if not json_mode:
        paths["summary"] = meeting_dir / "summaries" / f"round-{tag}-{guest}.summary.md"
    return paths