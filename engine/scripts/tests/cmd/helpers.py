"""tests/cmd/helpers.py — thin subprocess wrapper for engine CLI integration tests."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# helpers.py lives at engine/scripts/tests/cmd/helpers.py
# parents[0]=cmd  parents[1]=tests  parents[2]=scripts
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]


def run_engine(*args: str, env: dict | None = None, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "engine", *args],
        capture_output=True,
        text=True,
        cwd=cwd or str(_SCRIPTS_DIR),
        env={**os.environ, **(env or {})},
    )
