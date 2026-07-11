#!/usr/bin/env bash
# Claimfold CLI 转发 — App 位于 apps/research_council/
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/apps/research_council/council.sh" "$@"