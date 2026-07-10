#!/usr/bin/env python3
"""Council Engine — thin entrypoint (council.sh → lib/engine.py)."""
from council.cli import main
from council.cli_runner import invoke_cli
from council import build_parser, run_one_parallel_round
from council.parsers import merge_guest_json_into_state
from council.state_store import load_state, save_state

__all__ = [
    "main",
    "build_parser",
    "invoke_cli",
    "merge_guest_json_into_state",
    "load_state",
    "save_state",
    "run_one_parallel_round",
]

if __name__ == "__main__":
    main()
