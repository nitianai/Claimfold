"""MeetingContextService — read facade + immutable per-round snapshot."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from council.claims import (
    format_prior_claims_for_prompt,
    select_claims_for_injection,
    validate_injection_text,
)
from council.context.market import read_market_context


@dataclass(frozen=True)
class RoundContextSnapshot:
    """Frozen context bundle shared by all guests in one parallel round."""

    meeting_id: str
    round_num: int
    state: dict[str, Any]
    market_context: str
    prior_claims: tuple[dict[str, Any], ...]
    prior_claims_text: str


class MeetingContextService:
    """Read facade over file-backed session context (files remain source of truth)."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root

    def snapshot_for_round(
        self,
        meeting_dir: Path,
        state: dict[str, Any],
        *,
        round_num: int,
    ) -> RoundContextSnapshot:
        state_copy = copy.deepcopy(state)
        market_context = read_market_context(meeting_dir)
        prior_claims = select_claims_for_injection(state_copy, self.data_root)
        prior_text = format_prior_claims_for_prompt(prior_claims)
        inject_errors = validate_injection_text(prior_text)
        if inject_errors:
            raise ValueError("prior_claims 注入校验失败: " + "; ".join(inject_errors))
        return RoundContextSnapshot(
            meeting_id=str(state_copy.get("meeting_id", meeting_dir.name)),
            round_num=round_num,
            state=state_copy,
            market_context=market_context,
            prior_claims=tuple(prior_claims),
            prior_claims_text=prior_text,
        )