"""Backward-compatible shim — use council.cli_parser."""
from council.cli_parser import build_parser, get_handlers

__all__ = ["build_parser", "get_handlers"]