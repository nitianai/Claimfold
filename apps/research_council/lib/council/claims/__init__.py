"""Claim（主张）领域模块 — 晋升、注入、回应、验收。"""

from council.adapters.claim_envelope import CLAIM_EVENT_SCHEMA_VERSION, ensure_claim_envelope
from council.claims.injection import (
    format_prior_claims_for_prompt,
    select_claims_for_injection,
    validate_injection_text,
)
from council.claims.invariants import (
    claims_views_hash,
    verify_index_rebuild_invariant,
    verify_ledger_monotonicity,
    verify_rebuild_roundtrip,
)
from council.claims.policy import (
    ALLOWED_EVIDENCE_DIRS,
    FORBIDDEN_INJECT_WORDS,
    NON_PROMOTION_MARKERS,
    RESPONSE_TYPES,
    validate_promotion_candidate,
    validate_scope,
)
from council.claims.respond import parse_claim_responses_from_raw
from council.claims.verify import verify_three_meeting_chain
from missionos.ledger.store import (
    append_event,
    claims_dir,
    ensure_claims_dir,
    ledger_path,
    load_events,
)

# claim_ledger 依赖 stream_isolation；须在子模块之后导入以避免循环
from council.adapters.claim_ledger import (  # noqa: E402
    append_claim_event,
    append_promote_event,
    compute_fingerprint,
    fold_claims,
    index_path,
    load_claim_index,
    load_index,
    next_claim_id,
    rebuild_claim_index,
    rebuild_index,
)

__all__ = [
    "ALLOWED_EVIDENCE_DIRS",
    "FORBIDDEN_INJECT_WORDS",
    "NON_PROMOTION_MARKERS",
    "RESPONSE_TYPES",
    "CLAIM_EVENT_SCHEMA_VERSION",
    "append_claim_event",
    "append_event",
    "append_promote_event",
    "claims_views_hash",
    "ensure_claim_envelope",
    "claims_dir",
    "compute_fingerprint",
    "ensure_claims_dir",
    "fold_claims",
    "format_prior_claims_for_prompt",
    "index_path",
    "ledger_path",
    "load_events",
    "load_index",
    "next_claim_id",
    "parse_claim_responses_from_raw",
    "rebuild_index",
    "select_claims_for_injection",
    "validate_injection_text",
    "validate_promotion_candidate",
    "validate_scope",
    "verify_index_rebuild_invariant",
    "verify_ledger_monotonicity",
    "verify_rebuild_roundtrip",
    "verify_three_meeting_chain",
]