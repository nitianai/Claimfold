"""Safe artifact path construction under a session directory."""

from __future__ import annotations

import re
from pathlib import Path

_SAFE_SEGMENT = re.compile(r"^[\w.-]+$")


def _safe_segment(label: str, value: str) -> str:
    segment = (value or "").strip()
    if not segment or not _SAFE_SEGMENT.match(segment):
        raise SystemExit(f"Invalid {label}: {value!r}")
    if ".." in segment or "/" in segment or "\\" in segment:
        raise SystemExit(f"Invalid {label}: {value!r}")
    return segment


def safe_artifact_path(
    session_dir: Path,
    kind: str,
    participant_id: str,
    round_id: str,
) -> Path:
    """Return ``session_dir/kind/round-{round_id}-{participant_id}`` without traversal."""
    k = _safe_segment("kind", kind)
    participant = _safe_segment("participant_id", participant_id)
    round_tag = _safe_segment("round_id", round_id)
    root = session_dir.resolve()
    path = (root / k / f"round-{round_tag}-{participant}").resolve()
    if not path.is_relative_to(root):
        raise SystemExit(f"Artifact path escapes session dir: {path}")
    return path