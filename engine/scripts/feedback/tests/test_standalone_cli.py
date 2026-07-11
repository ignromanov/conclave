"""test_standalone_cli.py — verify all 5 CLI scripts run standalone without PYTHONPATH.

RED: fails before sys.path shim is added (ModuleNotFoundError: No module named 'briefing')
GREEN: passes after shim is inserted into each script.

Each script is invoked as a subprocess with PYTHONPATH completely absent from
the environment, proving the script self-bootstraps its import path.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FEEDBACK_PKG = Path(__file__).parent.parent  # .../scripts/feedback/

# Env with PYTHONPATH scrubbed — only bare OS vars needed for python to run.
_CLEAN_ENV: dict[str, str] = {
    k: v for k, v in os.environ.items()
    if k not in ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME")
}


def _run(script: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FEEDBACK_PKG / script), *args],
        capture_output=True,
        text=True,
        env=_CLEAN_ENV,
    )


# ---------------------------------------------------------------------------
# One test per script
# ---------------------------------------------------------------------------

def test_feedback_triage_standalone() -> None:
    result = _run("feedback_triage.py", ["--check"])
    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr


def test_feedback_index_standalone() -> None:
    result = _run("feedback_index.py", ["--check"])
    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr


def test_feedback_emit_standalone() -> None:
    result = _run("feedback_emit.py", ["--help"])
    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr


def test_feedback_migrate_standalone() -> None:
    result = _run("feedback_migrate.py", ["--help"])
    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr


def test_feedback_archive_standalone() -> None:
    result = _run("feedback_archive.py", ["--help"])
    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
