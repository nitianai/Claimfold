"""ContextPack — versioned manifest + body for shared session context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from missionos.utils import atomic_write_json

CONTEXT_PACK_VERSION = "1.0"
DEFAULT_BODY_FILENAME = "market_context.md"
DEFAULT_LEGACY_JSON_FILENAME = "market_context.json"
MANIFEST_FILENAME = "manifest.json"


def _body_checksum(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass
class ContextPack:
    version: str
    scope: str
    topic: str
    generated_at: str
    body_path: str
    checksum: str
    metadata: dict[str, Any]

    @classmethod
    def write(
        cls,
        context_dir: Path,
        *,
        body: str,
        scope: str,
        topic: str,
        generated_at: str,
        metadata: dict[str, Any] | None = None,
        body_filename: str = DEFAULT_BODY_FILENAME,
        legacy_json_filename: str = DEFAULT_LEGACY_JSON_FILENAME,
    ) -> tuple[Path, Path, Path]:
        """Write body, manifest, and legacy JSON index. Returns (body, manifest, legacy) paths."""
        context_dir.mkdir(parents=True, exist_ok=True)
        body_text = body.strip() + "\n"
        meta = dict(metadata or {})

        md_path = context_dir / body_filename
        md_path.write_text(body_text, encoding="utf-8")

        checksum = _body_checksum(body_text)
        manifest = {
            "version": CONTEXT_PACK_VERSION,
            "scope": scope,
            "topic": topic,
            "generated_at": generated_at,
            "body_path": body_filename,
            "checksum": checksum,
            "metadata": meta,
        }
        manifest_path = context_dir / MANIFEST_FILENAME
        atomic_write_json(manifest_path, manifest)

        legacy_payload = {
            "generated_at": generated_at,
            "scope": scope,
            "topic": topic,
            "body_md": body_text.strip(),
            **meta,
        }
        legacy_path = context_dir / legacy_json_filename
        atomic_write_json(legacy_path, legacy_payload)

        return md_path, manifest_path, legacy_path

    @classmethod
    def load(cls, context_dir: Path) -> ContextPack | None:
        manifest_path = context_dir / MANIFEST_FILENAME
        if not manifest_path.exists():
            return None
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return cls(
            version=str(data.get("version", CONTEXT_PACK_VERSION)),
            scope=str(data.get("scope", "")),
            topic=str(data.get("topic", "")),
            generated_at=str(data.get("generated_at", "")),
            body_path=str(data.get("body_path", DEFAULT_BODY_FILENAME)),
            checksum=str(data.get("checksum", "")),
            metadata=dict(data.get("metadata") or {}),
        )

    def read_body(self, context_dir: Path) -> str:
        path = context_dir / self.body_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def verify_checksum(self, context_dir: Path) -> bool:
        body = self.read_body(context_dir)
        if not body:
            return not self.checksum
        normalized = body.strip() + "\n"
        return _body_checksum(normalized) == self.checksum