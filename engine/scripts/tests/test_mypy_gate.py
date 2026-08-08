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


# Naming every package is the point. The gate used to pass `enginelib engine` and rely on mypy
# following imports to reach the rest — but WHICH files that reaches is a property of the
# environment, not of the gate: in CI it checked 82 of 169 files, while a dev box whose editable
# install pointed at a deleted directory resolved the same two packages off the filesystem and
# checked a different 82. A real error in evals/power.py was therefore red locally and green in
# CI for as long as both were true. Coverage belongs to the gate, not to whoever runs it.
CHECKED_PACKAGES = (
    "briefing", "critic", "engine", "enginelib", "evals", "feedback",
    "init", "judge", "lib", "lifecycle", "ranker",
)


def _packages_on_disk() -> set[str]:
    return {
        p.name for p in SCRIPTS_ROOT.iterdir()
        if p.is_dir()
        and not p.name.startswith((".", "_"))
        and p.name != "tests"
        and any(p.rglob("*.py"))  # `hooks/` ships shell only — nothing for mypy to read
    }


def test_mypy_gate_lists_every_package():
    """An enumeration with no completeness check rots the day someone adds a package.

    Without this, a new top-level package is simply never type-checked and the suite still
    reports green — the same silence that let the enginelib/engine list stand.
    """
    missing = _packages_on_disk() - set(CHECKED_PACKAGES)
    assert not missing, (
        f"packages exist but are not type-checked: {sorted(missing)}. "
        f"Add them to CHECKED_PACKAGES (and fix what mypy then finds)."
    )


def test_mypy_gate_lists_no_phantom_package():
    stale = set(CHECKED_PACKAGES) - _packages_on_disk()
    assert not stale, (
        f"CHECKED_PACKAGES names packages that no longer exist: {sorted(stale)}. "
        f"mypy fails outright on a missing directory, so this would break the gate."
    )


def test_mypy_check_is_clean():
    mypy = _mypy_cmd()
    if mypy is None:
        pytest.skip("mypy not installed (dev dependency); gate is a no-op outside dev/CI")
    result = subprocess.run(
        [*mypy, "--config-file", "pyproject.toml", *CHECKED_PACKAGES],
        cwd=SCRIPTS_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"mypy found type errors in {', '.join(CHECKED_PACKAGES)}:"
        f"\n{result.stdout}{result.stderr}"
    )
