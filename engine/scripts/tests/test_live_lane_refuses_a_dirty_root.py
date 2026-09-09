"""The live lane runs against a committed tree, or it does not run (GH#131 finding 4).

The `live_instance` lane is the only place in this suite where tests read and write a tree
the operator is actually using. It has already cost 34 DATA files: a run in non-hermetic
mode rewrote the frontmatter of 16 decisions and 18 session records from inside a test that
names itself a safety gate. The loss was total because the tree was dirty — committed, the
same run is a diff to read and revert.

GH#131 finding 4 asked for a sentence in `session-lifecycle.md`. A sentence would have been
read by the same person who was about to run the lane anyway. The precondition is enforced
in `_live_instance_root` instead, and pinned here.

Every case drives the REAL fixture through a real pytest subprocess rather than calling an
extracted predicate. The behaviour under test is a fixture's refusal, and a re-implementation
of its condition in the test would pass whether or not the fixture consults it — the shape
`test_root_resolver_agreement.py` was rewritten to escape.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: One `live_instance`-marked node. Which one does not matter: the refusal happens in an
#: autouse fixture, before the test body, so the assertion is about the fixture.
_MARKED_NODE = "engine/scripts/tests/briefing/test_paths.py::test_repo_root_returns_path"

_REFUSAL = "has uncommitted changes to"


def _git(path: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=str(path), check=True, capture_output=True,
    )


def _instance_tree(base: Path, name: str) -> Path:
    """A directory shaped enough like an instance root for the fixture to accept it."""
    root = base / name
    (root / "ops").mkdir(parents=True)
    (root / ".claude").mkdir(parents=True)
    (root / "roster.yaml").write_text("github: {}\n", encoding="utf-8")
    return root


def _run_lane(live_root: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()}
    env["CONCLAVE_LIVE_INSTANCE_ROOT"] = str(live_root)
    return subprocess.run(
        [sys.executable, "-m", "pytest", _MARKED_NODE, "-p", "no:cacheprovider"],
        cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True, timeout=300,
    )


def test_a_live_root_with_uncommitted_tracked_changes_is_refused(tmp_path):
    """The incident's own precondition: a tracked file edited but not committed."""
    root = _instance_tree(tmp_path, "dirty")
    _git(root, "init", "-q", "-b", "main", ".")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    (root / "roster.yaml").write_text("github: {edited: true}\n", encoding="utf-8")

    r = _run_lane(root)
    shown = r.stdout + r.stderr

    assert r.returncode != 0, f"the lane accepted a dirty live root:\n{shown}"
    assert _REFUSAL in shown, (
        f"the lane failed, but not for the dirty tree — a refusal for some other reason "
        f"is not this guard working:\n{shown}"
    )
    assert "roster.yaml" in shown, (
        f"the refusal must name the files at risk, or the reader cannot act on it:\n{shown}"
    )


def test_a_committed_live_root_is_accepted(tmp_path):
    """The other half. Without it the guard could refuse everything and still look right."""
    root = _instance_tree(tmp_path, "clean")
    _git(root, "init", "-q", "-b", "main", ".")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")

    r = _run_lane(root)
    shown = r.stdout + r.stderr

    assert _REFUSAL not in shown, (
        f"a committed tree was refused as dirty:\n{shown}"
    )


def test_a_live_root_outside_any_git_tree_is_accepted(tmp_path):
    """`engine test live` scaffolds a throwaway instance that git does not track.

    It has nothing to lose and must not be blocked. This is also why the predicate asks
    only about TRACKED files: a fresh seed landing inside this checkout is entirely
    untracked, and counting untracked files would fail the lane in exactly the case where
    the tree is disposable.
    """
    root = _instance_tree(tmp_path, "untracked")

    r = _run_lane(root)
    shown = r.stdout + r.stderr

    assert _REFUSAL not in shown, (
        f"a throwaway instance outside any git tree was refused as dirty:\n{shown}"
    )
