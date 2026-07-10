#!/usr/bin/env bash
# Council Engine V0.1 — deterministic multi-model meeting workflow runtime.
# Engine does NOT reason. Guests reason. Summarizer compresses. Owner controls.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/lib/engine.py" "$@"