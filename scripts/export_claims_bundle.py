#!/usr/bin/env python3
"""Export claims bundle — claims.jsonl + rebuilt index + manifest (sha256)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "platform"))
sys.path.insert(0, str(ROOT / "apps" / "research_council" / "lib"))

from council.adapters.claim_ledger import index_path, rebuild_claim_index  # noqa: E402
from missionos.ledger.store import claims_dir, ledger_path  # noqa: E402


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_bundle(*, data_root: Path, output_dir: Path) -> Path:
    claims_root = claims_dir(data_root)
    ledger = ledger_path(data_root)
    if not ledger.is_file():
        raise SystemExit(f"claims ledger missing: {ledger}")

    index = rebuild_claim_index(data_root)
    idx_file = index_path(data_root)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bundle_dir = output_dir / f"claims-bundle-{stamp}"
    bundle_dir.mkdir(parents=True, exist_ok=False)

    shutil.copy2(ledger, bundle_dir / "claims.jsonl")
    shutil.copy2(idx_file, bundle_dir / "claims_index.json")

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_root": str(data_root),
        "claim_count": index.get("claim_count", 0),
        "files": {
            "claims.jsonl": {"sha256": _sha256_file(bundle_dir / "claims.jsonl")},
            "claims_index.json": {"sha256": _sha256_file(bundle_dir / "claims_index.json")},
        },
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundle_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Export claims ledger bundle with manifest")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output parent directory (default: <data_root>/exports)",
    )
    args = parser.parse_args()

    data_root = Path(os.environ.get("COUNCIL_DATA_ROOT", str(ROOT))).resolve()
    output_dir = args.output or (data_root / "exports")
    output_dir.mkdir(parents=True, exist_ok=True)

    bundle_dir = export_bundle(data_root=data_root, output_dir=output_dir)
    print(f"Exported: {bundle_dir}")
    print(f"Manifest: {bundle_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()