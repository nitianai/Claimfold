"""ContextPack platform tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from missionos.context import CONTEXT_PACK_VERSION, ContextPack


def test_context_pack_write_load_and_legacy_json():
    with tempfile.TemporaryDirectory() as tmp:
        context_dir = Path(tmp) / "context"
        body = "# Market Context\n\nGold up 1%."
        md_path, manifest_path, legacy_path = ContextPack.write(
            context_dir,
            body=body,
            scope="gold, usd",
            topic="macro",
            generated_at="2026-07-11T12:00:00Z",
            metadata={"date": "2026-07-11", "used_mock": False, "equity_feeds": []},
        )

        assert md_path.name == "market_context.md"
        assert manifest_path.name == "manifest.json"
        assert legacy_path.name == "market_context.json"
        assert md_path.read_text(encoding="utf-8").strip() == body.strip()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["version"] == CONTEXT_PACK_VERSION
        assert manifest["scope"] == "gold, usd"
        assert manifest["body_path"] == "market_context.md"
        assert manifest["metadata"]["used_mock"] is False

        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        assert legacy["scope"] == "gold, usd"
        assert legacy["body_md"] == body.strip()
        assert legacy["date"] == "2026-07-11"

        pack = ContextPack.load(context_dir)
        assert pack is not None
        assert pack.read_body(context_dir) == body.strip()
        assert pack.verify_checksum(context_dir)