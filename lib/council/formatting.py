"""Text formatting and artifact path helpers."""
from __future__ import annotations

from pathlib import Path


def format_list(items: list[str], empty: str = "(无)") -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def format_guest_summaries(summaries: dict[str, str]) -> str:
    if not summaries:
        return "(无)"
    lines = []
    for guest, summary in summaries.items():
        lines.append(f"### {guest}")
        lines.append(summary.strip() or "(空)")
    return "\n".join(lines)


def render_template(template_path: Path, variables: dict[str, str]) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def round_tag(n: int) -> str:
    return f"{n:03d}"


def artifact_paths(meeting_dir: Path, round_num: int, guest: str, *, json_mode: bool = True) -> dict[str, Path]:
    tag = round_tag(round_num)
    paths = {
        "prompt": meeting_dir / "prompts" / f"round-{tag}-{guest}.prompt.md",
        "raw": meeting_dir / "raw" / f"round-{tag}-{guest}.{'json' if json_mode else 'md'}",
    }
    if not json_mode:
        paths["summary"] = meeting_dir / "summaries" / f"round-{tag}-{guest}.summary.md"
    return paths
