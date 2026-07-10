#!/usr/bin/env bash
# Point this repo at .githooks/ so pre-push runs ./scripts/ci.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

chmod +x scripts/ci.sh .githooks/pre-push

git config core.hooksPath .githooks

echo "Git hooks installed: core.hooksPath=.githooks"
echo "  pre-push → scripts/ci.sh (16 regression tests + smoke)"
echo ""
echo "Manual run: ./scripts/ci.sh"