"""Mock semantic item detection for summary merge."""

from __future__ import annotations

from council.claims.policy import NON_PROMOTION_MARKERS


def is_mock_semantic_item(item: str) -> bool:
    text = (item or "").strip()
    if not text:
        return True
    if text.startswith("[MOCK") or text.startswith("MOCK/"):
        return True
    return any(marker in text for marker in NON_PROMOTION_MARKERS)