"""Import boundary: missionos must not pull App modules."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PLATFORM = ROOT / "platform"


def _run_import_probe() -> str:
    code = """
import sys
sys.path.insert(0, %r)
import missionos
loaded = sorted(m for m in sys.modules if m.startswith(("council", "runtime_ext", "claim_lifecycle", "engine")))
if loaded:
    raise SystemExit("forbidden modules loaded: " + ", ".join(loaded))
print("missionos import clean")
""" % str(PLATFORM)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise AssertionError((result.stderr or result.stdout or "import probe failed").strip())
    return (result.stdout or "").strip()


def test_missionos_import_does_not_load_app_modules():
    out = _run_import_probe()
    assert "clean" in out


def test_check_platform_boundary_script_passes():
    script = ROOT / "scripts" / "check_platform_boundary.sh"
    assert script.is_file(), f"missing {script}"
    result = subprocess.run([str(script)], capture_output=True, text=True, cwd=str(ROOT))
    assert result.returncode == 0, (result.stderr or result.stdout or "boundary check failed").strip()