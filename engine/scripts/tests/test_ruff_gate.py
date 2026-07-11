"""test_ruff_gate.py — enforce `ruff check` cleanliness as part of the suite (spec 099, F5).

Nothing else ran ruff (no CI/pre-commit hook), so lint debt accumulated silently during the
bash->Python port. This gate makes the enforced rule set (E/F/I/UP/B minus the E501/E402 carve-outs
configured in pyproject.toml [tool.ruff.lint]) a suite invariant: any new violation fails a test.

E501 (line-too-long) is deliberately ignored in config — line-length belongs to a formatter; adopt
`ruff format` in a follow-up and drop the ignore. This gate enforces everything else.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

# tests/ -> scripts/ ; ruff runs against the project root where pyproject.toml lives.
SCRIPTS_ROOT = Path(__file__).resolve().parents[1]


def test_ruff_check_is_clean():
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff not installed (dev dependency); gate is a no-op outside dev/CI")
    result = subprocess.run(
        [ruff, "check", "--output-format=concise"],
        cwd=SCRIPTS_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "ruff found lint violations (enforced rule set = E/F/I/UP/B minus configured "
        f"E501/E402 carve-outs):\n{result.stdout}{result.stderr}"
    )
