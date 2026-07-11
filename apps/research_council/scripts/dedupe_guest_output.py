#!/usr/bin/env python3
"""Drop duplicate trailing blocks in local guest CLI output (codex/qoder)."""
from __future__ import annotations

import sys

MARKERS = ("判断：", "判断:")


def dedupe(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    for marker in MARKERS:
        first = text.find(marker)
        if first == -1:
            continue
        second = text.find(marker, first + len(marker))
        if second != -1:
            return text[:second].rstrip() + "\n"
    # Fallback: exact duplicate halves
    half = len(text) // 2
    if half > 80 and text[:half].strip() == text[half:].strip():
        return text[:half].rstrip() + "\n"
    return text + ("\n" if not text.endswith("\n") else "")


if __name__ == "__main__":
    sys.stdout.write(dedupe(sys.stdin.read()))