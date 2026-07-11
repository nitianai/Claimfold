"""Claimfold council engine package — lazy re-exports to avoid import cycles."""

from __future__ import annotations

from typing import Any

__all__ = ["build_parser", "get_handlers", "run_one_parallel_round", "run_one_round"]


def __getattr__(name: str) -> Any:
    if name in ("build_parser", "get_handlers"):
        from council.cli_parser import build_parser, get_handlers

        return build_parser if name == "build_parser" else get_handlers
    if name == "run_one_parallel_round":
        from council.runners import run_one_parallel_round

        return run_one_parallel_round
    if name == "run_one_round":
        from council.runners import run_one_round

        return run_one_round
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")