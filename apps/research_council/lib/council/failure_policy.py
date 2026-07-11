"""FailurePolicy（失败策略）— parallel/interactive runner 共用。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from missionos.utils import utc_now

FAILURE_POLICIES = frozenset({"allow_partial", "all_must_succeed", "fail_fast"})
DEFAULT_FAILURE_POLICY = "allow_partial"


def resolve_failure_policy(state: dict[str, Any]) -> str:
    policy = str(state.get("failure_policy") or DEFAULT_FAILURE_POLICY).strip()
    if policy not in FAILURE_POLICIES:
        return DEFAULT_FAILURE_POLICY
    return policy


def default_hitl_config(owner_pause: int) -> dict[str, Any]:
    return {
        "every_n_rounds": owner_pause,
        "require_before_promote": False,
        "open": False,
        "reason": "",
        "round": 0,
        "last_resolved_action": "",
    }


def ensure_runtime_policy_fields(state: dict[str, Any]) -> None:
    if "failure_policy" not in state:
        state["failure_policy"] = DEFAULT_FAILURE_POLICY
    if "partial_warnings" not in state:
        state["partial_warnings"] = []
    if "hitl" not in state:
        state["hitl"] = default_hitl_config(state.get("max_round_before_owner", 3))


def skip_guest_entry(guest_name: str, *, reason: str) -> dict[str, Any]:
    return {
        "guest": guest_name,
        "success": False,
        "skipped": True,
        "error": reason,
        "duration_s": 0.0,
        "respond_events": [],
    }


def run_round_guests(
    *,
    policy: str,
    selected: list[str],
    parallel_batch: list[str],
    serial_batch: list[str],
    max_workers: int,
    run_guest: Callable[[str], dict[str, Any]],
    skip_guest: Callable[[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    if policy == "fail_fast":
        halted = False
        for guest_name in selected:
            if halted:
                entries.append(skip_guest(guest_name, "fail_fast: prior guest failed"))
                continue
            entry = run_guest(guest_name)
            entries.append(entry)
            if not entry.get("success"):
                halted = True
        return entries

    if parallel_batch:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(parallel_batch))) as pool:
            futures = {pool.submit(run_guest, g): g for g in parallel_batch}
            for fut in as_completed(futures):
                entries.append(fut.result())
    for guest_name in serial_batch:
        entries.append(run_guest(guest_name))

    entries.sort(key=lambda e: selected.index(e["guest"]) if e["guest"] in selected else 999)
    return entries


def apply_failure_policy_after_round(
    state: dict[str, Any],
    *,
    entries: list[dict[str, Any]],
    policy: str,
    round_num: int,
) -> str | None:
    """按策略处理轮次结果；若需 Owner 介入则返回 interrupt reason。"""
    failed = [e for e in entries if not e.get("success") and not e.get("skipped")]
    succeeded = [e for e in entries if e.get("success")]

    if policy == "allow_partial":
        if failed and succeeded:
            state.setdefault("partial_warnings", []).append(
                {
                    "round": round_num,
                    "failed_guests": [e["guest"] for e in failed],
                    "succeeded_guests": [e["guest"] for e in succeeded],
                    "ts": utc_now(),
                }
            )
        return None

    if policy == "all_must_succeed" and failed:
        state["owner_required"] = True
        return "guest_failure"

    return None


def owner_pause_reason(state: dict[str, Any]) -> str | None:
    if state.get("rounds_since_owner", 0) >= state.get("max_round_before_owner", 3):
        return "every_n_rounds"
    return None