"""test_mypy_gate.py — enforce `mypy` cleanliness as part of the suite.

mypy was configured in pyproject.toml [tool.mypy] and declared in dev deps, but nothing ever
invoked it — a real signature error (enginelib/post_commit.py calling
advisors_from_commit_diff() without its required `advisors` argument) shipped undetected and
raised TypeError on every real commit that installs the git hook. This gate makes `mypy`
cleanliness a suite invariant: any new type error fails a test instead of lying dormant.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# tests/ -> scripts/ ; mypy runs against the project root where pyproject.toml lives.
SCRIPTS_ROOT = Path(__file__).resolve().parents[1]


def _mypy_cmd() -> list[str] | None:
    """Return the argv prefix that invokes mypy, or None if it is genuinely unavailable.

    PATH alone is not enough. `<venv>/bin/python -m pytest` (an unactivated venv — how CI and
    most tooling invoke the suite) leaves the venv's bin dir off PATH, so `shutil.which` misses
    a mypy that is installed in the very interpreter running these tests, and the gate skips
    itself while reporting green. Fall back to the module entry point before giving up.
    """
    exe = shutil.which("mypy")
    if exe is not None:
        return [exe]
    probe = subprocess.run(
        [sys.executable, "-m", "mypy", "--version"], capture_output=True, text=True
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "mypy"]
    return None


def test_mypy_check_is_clean():
    mypy = _mypy_cmd()
    if mypy is None:
        pytest.skip("mypy not installed (dev dependency); gate is a no-op outside dev/CI")
    result = subprocess.run(
        [*mypy, "--config-file", "pyproject.toml", "enginelib", "engine"],
        cwd=SCRIPTS_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"mypy found type errors in enginelib/engine:\n{result.stdout}{result.stderr}"
    )
