"""tests/cmd/helpers.py — thin subprocess wrapper + git-isolation helpers for CLI tests."""
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


def non_repo_dir(parent: Path, name: str = "not-a-repo") -> Path:
    """A scratch directory PROVEN to sit outside any git repository.

    For tests that pin `CONCLAVE_GIT_REMOTE_CWD` at a "not a repo" location so the
    git-remote fallback layer cannot reach a real checkout. That isolation used to be
    inherited from pytest's `tmp_path` happening to live outside any working tree — a
    `--basetemp` under the workspace would let `git remote get-url origin` walk UP, find the
    enclosing repository, and the pin would silently stop being a pin while every assertion
    still passed. So assert the premise instead of assuming it, and fail loudly (never skip)
    when it breaks: a test that cannot isolate itself has to say so.
    """
    target = parent / name
    target.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, cwd=str(target),
    )
    assert probe.returncode != 0, (
        f"{target} is inside the git repository at {probe.stdout.strip()!r}, so it cannot serve "
        f"as a non-repo pin: the git-remote fallback would resolve that repository's origin. "
        f"pytest's basetemp must live outside any checkout."
    )
    return target


def make_git_repo(path: Path, branch: str = "consumer-main", origin: str | None = None) -> Path:
    """A real, committed git repository at `path` — for tests that must give a layered
    resolver a WORKING lower layer rather than a dead one.

    A resolver that is supposed to REFUSE at layer 1 cannot be tested against a layer 2 that
    yields nothing anyway: the assertion passes whether layer 1 refused or fell through to a
    dead end. Only a reachable, resolvable layer 2 tells the two apart.
    """
    path.mkdir(parents=True, exist_ok=True)
    git = ["git", "-c", "user.email=test@conclave", "-c", "user.name=test"]
    subprocess.run(["git", "init", "-q", "-b", branch, "."], cwd=str(path), check=True)
    (path / "README.md").write_text("throwaway\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run([*git, "commit", "-qm", "init"], cwd=str(path), check=True, capture_output=True)
    if origin:
        subprocess.run(
            ["git", "remote", "add", "origin", origin],
            cwd=str(path), check=True, capture_output=True,
        )
    return path
