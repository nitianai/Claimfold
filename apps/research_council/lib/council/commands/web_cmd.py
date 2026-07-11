"""Council web UI server command."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def cmd_web(args: argparse.Namespace) -> None:
    app_dir = Path(__file__).resolve().parents[3]
    server_path = app_dir / "web" / "server.py"
    spec = importlib.util.spec_from_file_location("council_web_server", server_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Web server not found: {server_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["council_web_server"] = module
    spec.loader.exec_module(module)

    old_argv = sys.argv
    try:
        sys.argv = ["server.py", "--host", args.host, "--port", str(args.port)]
        module.main()
    finally:
        sys.argv = old_argv