"""tests/enginelib/test_doctor.py — #49(c) First-Launch preflight.

Hermetic: operates on tmp roots only.
"""
from __future__ import annotations

import subprocess

import pytest

from enginelib import doctor


def _mk_root(tmp_path):
    (tmp_path / "agent-memory").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _check(checks, name):
    return next(c for c in checks if c.name == name)


def test_missing_hot_reported_not_ok(tmp_path):
    root = _mk_root(tmp_path)
    checks = doctor.run_checks(root)
    assert _check(checks, "hot.md").ok is False
    assert doctor.exit_code(checks) != 0


def test_fix_seeds_hot_skeleton(tmp_path):
    root = _mk_root(tmp_path)
    checks = doctor.run_checks(root, fix=True)
    hot = root / "agent-memory" / "hot.md"
    assert hot.is_file()
    text = hot.read_text(encoding="utf-8")
    for header in ("## Now", "## Recent decisions", "## Watch"):
        assert header in text
    assert _check(checks, "hot.md").ok is True


def test_wellformed_hot_is_ok(tmp_path):
    root = _mk_root(tmp_path)
    (root / "agent-memory" / "hot.md").write_text(
        "## Now\n\n## Open threads\n\n## Recent decisions\n\n## Watch\n", encoding="utf-8"
    )
    checks = doctor.run_checks(root)
    assert _check(checks, "hot.md").ok is True


def test_malformed_hot_flagged_and_not_clobbered_without_fix(tmp_path):
    root = _mk_root(tmp_path)
    hot = root / "agent-memory" / "hot.md"
    hot.write_text("garbage no sections here\n", encoding="utf-8")
    checks = doctor.run_checks(root)
    assert _check(checks, "hot.md").ok is False
    # Content preserved (never silently overwritten without --fix).
    assert hot.read_text(encoding="utf-8") == "garbage no sections here\n"


def test_advisor_in_registry_ok(tmp_path):
    root = _mk_root(tmp_path)
    (root / ".claude" / "agents" / "sage-cto.md").write_text("# advisor\n", encoding="utf-8")
    checks = doctor.run_checks(root, advisor="sage-cto")
    assert _check(checks, "advisor:sage-cto").ok is True


def test_advisor_not_in_registry_flagged(tmp_path):
    root = _mk_root(tmp_path)
    checks = doctor.run_checks(root, advisor="ghost")
    assert _check(checks, "advisor:ghost").ok is False
    assert doctor.exit_code(checks) != 0


def test_forge_meta_advisor_accepted(tmp_path):
    root = _mk_root(tmp_path)
    checks = doctor.run_checks(root, advisor="forge-chro")
    assert _check(checks, "advisor:forge-chro").ok is True


# ---------------------------------------------------------------------------
# merge-base check (#58) — a branch with no common ancestor cannot be merged at all.
# ---------------------------------------------------------------------------

def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(repo),
             "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"},
    )


@pytest.fixture
def repo(tmp_path):
    """A real repo on `master` with one commit. Real git, because the whole point is
    what `git merge-base` actually returns — a stubbed one would only re-assert my
    reading of the manual."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "master")
    (r / "a.txt").write_text("a\n")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-qm", "first")
    return r


def test_shared_history_branch_is_ok(repo):
    _git(repo, "branch", "feature")
    checks = doctor.run_checks(repo, repos=[repo])
    assert _check(checks, "merge-base").ok is True


def test_orphan_branch_is_flagged(repo):
    """The 104-P0 and 105 lanes are in exactly this state: real commits on a branch
    that shares no ancestor with master, so `git merge` can never integrate them."""
    _git(repo, "checkout", "-q", "--orphan", "stranded")
    (repo / "b.txt").write_text("b\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-qm", "orphan work")

    checks = doctor.run_checks(repo, repos=[repo])
    mb = _check(checks, "merge-base")
    assert mb.ok is False
    assert "stranded" in mb.detail
    assert doctor.exit_code(checks) != 0


def test_same_repo_passed_twice_is_reported_once(repo):
    """CODE root and engine root are different paths in one repository; a single-repo
    instance adds the DATA root as a third. Without dedup by git toplevel the same
    stranded branch is reported once per path and the count stops meaning anything."""
    _git(repo, "checkout", "-q", "--orphan", "stranded")
    (repo / "b.txt").write_text("b\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-qm", "orphan work")
    sub = repo / "engine"
    sub.mkdir()

    detail = _check(doctor.run_checks(repo, repos=[repo, sub]), "merge-base").detail
    assert detail.count("stranded") == 1, detail


def test_non_git_path_is_not_a_finding(tmp_path):
    """Absence of a repo is not a broken repo — a check that cannot run must not
    manufacture a failure any more than it may manufacture a pass."""
    checks = doctor.run_checks(tmp_path, repos=[tmp_path])
    assert _check(checks, "merge-base").ok is True
