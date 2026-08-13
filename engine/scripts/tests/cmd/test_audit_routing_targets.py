"""`engine audit routing-targets` resolves the shipped commands and exits 0 when clean."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def _run() -> subprocess.CompletedProcess[str]:
    # CONCLAVE_ENGINE_ROOT must be pinned to the tree under test. paths.py:41-44 prefers the
    # env var over the source-relative fallback, and in a git worktree that variable is
    # inherited from the MAIN checkout — so an unpinned subprocess audits a different tree
    # and reports its verdict as this one's. Measured in worktrees/108-p1-subtraction:
    # engine_root() returned /Users/ignat/code/conclave/engine, not the worktree's. GH#86.
    env = {**os.environ, "CONCLAVE_ENGINE_ROOT": str(REPO / "engine")}
    return subprocess.run(
        [sys.executable, "-m", "engine", "audit", "routing-targets"],
        cwd=REPO / "engine" / "scripts",
        capture_output=True,
        text=True,
        env=env,
    )


def test_the_audit_name_is_registered():
    assert "invalid choice" not in _run().stderr


def test_the_audit_exits_zero_on_a_clean_tree():
    proc = _run()
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_audit_prints_a_summary_line():
    assert "=== Summary:" in _run().stdout
