"""Research workflow verification helpers."""

from __future__ import annotations

import json
from pathlib import Path

from council.parsers.mock_filter import is_mock_semantic_item


def verify_research_semantic_loop(meeting_dir: Path, round_num: int = 2) -> tuple[bool, list[str]]:
    """Verify MERGE→ACT feedback: round N prompt/raw must carry round N-1 semantic items."""
    errors: list[str] = []
    tag_prev = f"{round_num - 1:03d}"
    tag_curr = f"{round_num:03d}"

    prior_items: list[str] = []
    for path in (meeting_dir / "summaries").glob(f"round-{tag_prev}-*.summary.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"invalid summary json: {path.name}")
            continue
        for key in ("confirmed_points", "conflicts", "open_questions"):
            prior_items.extend(
                item for item in data.get(key, []) if item and not is_mock_semantic_item(item)
            )

    if not prior_items:
        errors.append(f"round {tag_prev} produced no confirmed/conflicts/open_questions in summary.json")

    prompts = list((meeting_dir / "prompts").glob(f"round-{tag_curr}-*.prompt.md"))
    raws = list((meeting_dir / "raw").glob(f"round-{tag_curr}-*.md"))
    if not prompts:
        errors.append(f"no round {tag_curr} prompts found")
    if not raws:
        errors.append(f"no round {tag_curr} raw files found")

    required_sections = ("## 当前已确认观点", "## 当前分歧", "## 当前未决问题")
    for section in required_sections:
        if prompts and not any(section in p.read_text(encoding="utf-8") for p in prompts):
            errors.append(f"round {tag_curr} prompt missing section: {section}")

    if prior_items and prompts:
        prompt_hit = any(
            any(item in p.read_text(encoding="utf-8") for item in prior_items) for p in prompts
        )
        if not prompt_hit:
            errors.append(f"round {tag_curr} prompt does not contain round {tag_prev} semantic items")

    if prior_items and raws:
        raw_hit = any(any(item in r.read_text(encoding="utf-8") for item in prior_items) for r in raws)
        if not raw_hit:
            errors.append(f"round {tag_curr} raw does not reference round {tag_prev} semantic items")

    return len(errors) == 0, errors