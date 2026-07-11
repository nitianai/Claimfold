"""Phase 4: compatibility shims must be removed."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
APP = ROOT / "apps" / "research_council"

_REMOVED_SHIMS = (
    APP / "lib" / "utils.py",
    APP / "lib" / "claim_lifecycle.py",
    APP / "lib" / "council" / "parser.py",
    APP / "lib" / "council" / "plan" / "runtime.py",
    APP / "lib" / "council" / "commands" / "meeting.py",
    APP / "lib" / "council" / "commands" / "daily_cmd.py",
)


def test_compat_shims_removed():
    for path in _REMOVED_SHIMS:
        assert not path.is_file(), f"compat shim must be removed: {path}"