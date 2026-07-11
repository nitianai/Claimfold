"""CouncilSessionAdapter（委员会会话适配器）— Meeting 语义与 Artifact（制品）路径。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from council.config import DATA_ROOT
from missionos.protocols import SessionStoreProtocol
from missionos.session import SessionStore, safe_artifact_path
from missionos.utils import validate_meeting_id

_SESSION_STORE: SessionStoreProtocol = SessionStore(root=DATA_ROOT)


def get_current_meeting_dir() -> Path:
    if not _SESSION_STORE.pointer_path.exists():
        raise SystemExit('No active meeting. Run: ./council.sh start "议题"')
    meeting_id = validate_meeting_id(_SESSION_STORE.read_pointer())
    meeting_dir = _SESSION_STORE.resolve_session_dir(meeting_id, validate_fn=validate_meeting_id)
    if not meeting_dir.exists():
        raise SystemExit(f"Meeting directory missing: {meeting_dir}")
    return meeting_dir


def artifact_paths_research(
    meeting_dir: Path, round_num: int, guest: str, round_tag: Callable[[int], str]
) -> dict[str, Path]:
    tag = round_tag(round_num)
    return {
        "prompt": safe_artifact_path(meeting_dir, "prompts", guest, tag).with_name(
            f"round-{tag}-{guest}.prompt.md"
        ),
        "raw": safe_artifact_path(meeting_dir, "raw", guest, tag).with_suffix(".md"),
        "summary_md": safe_artifact_path(meeting_dir, "summaries", guest, tag).with_name(
            f"round-{tag}-{guest}.summary.md"
        ),
        "summary_json": safe_artifact_path(meeting_dir, "summaries", guest, tag).with_name(
            f"round-{tag}-{guest}.summary.json"
        ),
        "error": safe_artifact_path(meeting_dir, "errors", guest, tag).with_suffix(".error.md"),
    }