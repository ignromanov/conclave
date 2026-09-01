"""#160 — a close must rest on evidence that shipped, not on the working tree."""
import subprocess

import pytest
from shipped import UNTRACKED_TREE, is_shipped, repo_of, shipped_ref


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path):
    """A repo with one committed file, plus an unrelated dir outside any repo."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "a.py").write_text("still has the BUG\n")
    _git(r, "add", "a.py")
    _git(r, "commit", "-qm", "seed")
    return r


def test_a_committed_unmodified_file_is_shipped(repo):
    ok, snapshot = is_shipped(repo / "a.py")
    assert ok is True
    assert "HEAD" in snapshot  # no upstream in a bare test repo — the floor


def test_an_uncommitted_edit_is_not_shipped(repo):
    """The measured scenario: the fix is on disk, in no commit, and the predicate would
    read it as done."""
    (repo / "a.py").write_text("the BUG is gone\n")
    ok, _ = is_shipped(repo / "a.py")
    assert ok is False


def test_an_untracked_file_is_not_shipped(repo):
    """`git diff <ref>` cannot see an untracked file, so it would read as unchanged. A
    file-contains predicate on a new test file lands exactly here."""
    (repo / "new_test.py").write_text("def test_thing(): ...\n")
    ok, _ = is_shipped(repo / "new_test.py")
    assert ok is False


def test_an_uncommitted_deletion_is_not_shipped(repo):
    """file-absent: the target is gone from disk but still in the ref."""
    (repo / "a.py").unlink()
    ok, _ = is_shipped(repo / "a.py")
    assert ok is False


def test_a_file_absent_from_both_is_shipped(repo):
    """A path that exists in neither the tree nor the ref is genuinely gone: a
    file-absent predicate on an already-deleted file must still be closable."""
    ok, snapshot = is_shipped(repo / "never-existed.py")
    assert ok is True
    # Pinned so the assertion cannot pass for the wrong reason: a stub returning True
    # unconditionally would satisfy the line above and name no snapshot at all.
    assert "HEAD" in snapshot


def test_a_tree_outside_any_repo_counts_as_shipped(tmp_path):
    """A marketplace plugin is unpacked, not cloned — no git, and what is on disk IS the
    released artefact. Refusing to close there would strand every plugin-mode instance."""
    d = tmp_path / "plugin" / "engine"
    d.mkdir(parents=True)
    (d / "x.py").write_text("x\n")
    ok, snapshot = is_shipped(d / "x.py")
    assert ok is True
    assert snapshot == UNTRACKED_TREE


def test_committed_but_unmerged_work_is_not_shipped(repo):
    """The stronger half: committed is not shipped. With an upstream configured, a commit
    that has not landed there is still unshipped."""
    upstream = repo.parent / "upstream.git"
    _git(repo, "clone", "-q", "--bare", str(repo), str(upstream))
    _git(repo, "remote", "add", "origin", str(upstream))
    _git(repo, "fetch", "-q", "origin")
    _git(repo, "branch", "--set-upstream-to=origin/main", "main")
    repo_of.cache_clear()
    shipped_ref.cache_clear()

    assert is_shipped(repo / "a.py")[0] is True, "in sync with upstream"

    (repo / "a.py").write_text("the BUG is gone\n")
    _git(repo, "commit", "-qam", "fix, not pushed")
    ok, snapshot = is_shipped(repo / "a.py")
    assert ok is False, "a commit that never reached the upstream has not shipped"
    assert "origin/main" in snapshot
