"""`engine status` — the branch slot's gathering half (plan 057 T9).

The join itself is pinned in `tests/enginelib/test_status_branches.py` on plain
dataclasses. What is left here is the part that can only be wrong against a real
repository: which branches are seen at all, which signal each field is actually taken
from, and what the slot does when a signal cannot be taken.

The last of those is the one with history. This projection's whole premise (rule 6) is
that "measured zero" and "did not measure" must not render alike, and the branch slot is
the first one whose sources can fail INDEPENDENTLY — `gh` can be missing while git is
fine, and the network can be down while both binaries exist. A slot that answers "0
branches need attention" because `gh` was not installed is the exact failure this
command was filed against.
"""
from __future__ import annotations

import subprocess

import pytest

from engine.cmd import status as status_cmd
from enginelib.status.branches import PullRequest
from enginelib.status.model import Absent, Count
from enginelib.status.words import say

GIT = ["git", "-c", "user.email=t@conclave", "-c", "user.name=t"]


def _run(repo, *args):
    return subprocess.run(
        [*GIT, *args], cwd=str(repo), check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A repo with a default branch and three branches in different states.

    `origin` is a real second repository rather than a stub, because the whole point of
    `BASE = origin/<default>` is that it is the ref that RECEIVED the merge; pointing it
    at the local branch of the same name reproduces the defect Step 4 warns about and
    the test would then pass on a wrong implementation.
    """
    upstream = tmp_path / "upstream.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(upstream)], check=True)

    work = tmp_path / "work"
    work.mkdir()
    _run(work, "init", "-q", "-b", "master")
    (work / "base.txt").write_text("base\n", encoding="utf-8")
    _run(work, "add", "-A")
    _run(work, "commit", "-qm", "base")
    _run(work, "remote", "add", "origin", str(upstream))
    _run(work, "push", "-q", "origin", "master")

    # shipped/: one commit, squashed onto master upstream — git cherry will NOT see it
    # as shipped, which is the blindness the fourth signal exists to cut through.
    _run(work, "checkout", "-q", "-b", "shipped")
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    _run(work, "add", "-A")
    _run(work, "commit", "-qm", "feature part 1")
    (work / "b.txt").write_text("b\n", encoding="utf-8")
    _run(work, "add", "-A")
    _run(work, "commit", "-qm", "feature part 2")
    shipped_head = _run(work, "rev-parse", "HEAD")

    _run(work, "push", "-q", "origin", "shipped")
    _run(work, "checkout", "-q", "master")
    _run(work, "merge", "-q", "--squash", "shipped")
    _run(work, "commit", "-qm", "feat: the two commits, squashed (#1)")
    _run(work, "push", "-q", "origin", "master")

    # …and the merge deletes the head branch on the server, which is what GitHub does
    # on a squash-merge. `git fetch` first, so this checkout ends up holding exactly the
    # state that caused the 2026-09-14 incident: refs/remotes/origin/shipped present
    # locally, refs/heads/shipped absent on the server. Nothing is pruned — pruning here
    # would repair the very condition under test.
    _run(work, "fetch", "-q", "origin")
    subprocess.run(
        ["git", "-C", str(upstream), "update-ref", "-d", "refs/heads/shipped"], check=True
    )

    # live/: unshipped work, an open PR in the fixture below
    _run(work, "checkout", "-q", "-b", "live", "master")
    (work / "c.txt").write_text("c\n", encoding="utf-8")
    _run(work, "add", "-A")
    _run(work, "commit", "-qm", "wip")

    # beyond/: shipped, then someone kept committing on top of the merged head
    _run(work, "checkout", "-q", "-b", "beyond", "shipped")
    (work / "d.txt").write_text("d\n", encoding="utf-8")
    _run(work, "add", "-A")
    _run(work, "commit", "-qm", "after the merge")

    # ffmerged/: shipped by an ordinary fast-forward, and then the LOCAL default branch
    # is rewound so it no longer contains it. `git fetch` advances origin/master and
    # never the local master, so this is the ordinary state of a checkout that has not
    # pulled — and it is the one Step 4 warns about hardest, because comparing against
    # the local default reports every branch merged since as unshipped.
    _run(work, "checkout", "-q", "-b", "ffmerged", "master")
    (work / "e.txt").write_text("e\n", encoding="utf-8")
    _run(work, "add", "-A")
    _run(work, "commit", "-qm", "plain merge, no squash")
    _run(work, "checkout", "-q", "master")
    _run(work, "merge", "-q", "--ff-only", "ffmerged")
    _run(work, "push", "-q", "origin", "master")
    _run(work, "reset", "-q", "--hard", "HEAD~1")

    # No `--prune`: pruning here would repair the ghost ref this fixture exists to hold.
    _run(work, "fetch", "-q", "origin")
    return work, shipped_head


def test_the_default_branch_is_never_a_row(repo):
    work, _ = repo
    facts = status_cmd._branch_facts(work, [], {"master"})
    assert "master" not in [f.name for f in facts]
    assert {f.name for f in facts} == {"shipped", "live", "beyond", "ffmerged"}


def test_cherry_reports_the_squashed_branch_as_unshipped(repo):
    """The premise of the fourth signal, measured rather than asserted.

    If this ever goes to 0, `git cherry` learned to see an N>1 squash and the extra
    signal is no longer load-bearing — which is a thing a future reader should be told
    by a red test, not discover by reading a docstring.
    """
    work, _ = repo
    shipped = next(f for f in status_cmd._branch_facts(work, [], {"master"}) if f.name == "shipped")
    assert shipped.unshipped == 2


def test_beyond_merge_is_measured_from_the_prs_frozen_head_oid(repo):
    work, shipped_head = repo
    prs = [
        ("shipped", PullRequest(number=1, state="MERGED", head_oid=shipped_head)),
        ("beyond", PullRequest(number=2, state="MERGED", head_oid=shipped_head)),
    ]
    facts = {f.name: f for f in status_cmd._branch_facts(work, prs, {"master"})}
    assert facts["shipped"].beyond_merge == 0
    assert facts["beyond"].beyond_merge == 1


def test_the_join_calls_the_squashed_branch_shipped_and_the_other_one_work(repo, monkeypatch):
    """End to end over a real squash: the two rows Step 4 cannot tell apart."""
    work, shipped_head = repo
    prs = [
        ("shipped", PullRequest(number=1, state="MERGED", head_oid=shipped_head)),
        ("beyond", PullRequest(number=2, state="MERGED", head_oid=shipped_head)),
        ("live", PullRequest(number=3, state="OPEN", head_oid="x")),
    ]
    monkeypatch.setattr(status_cmd, "_gh_pull_requests", lambda root: prs)
    monkeypatch.setattr(status_cmd, "_remote_heads", lambda root: {"master"})
    section = status_cmd._branches_section(work)
    rows = {r.name: r for r in section.rows}
    assert rows["shipped"].disposition == "shipped"
    assert rows["beyond"].disposition == "beyond_merge"
    assert rows["live"].disposition == "in_flight"


def test_a_branch_the_remote_still_holds_is_distinguished_from_a_ghost(repo, monkeypatch):
    work, shipped_head = repo
    prs = [("shipped", PullRequest(number=1, state="MERGED", head_oid=shipped_head))]
    monkeypatch.setattr(status_cmd, "_gh_pull_requests", lambda root: prs)
    monkeypatch.setattr(status_cmd, "_remote_heads", lambda root: {"master", "shipped"})
    still_there = {r.name: r for r in status_cmd._branches_section(work).rows}
    assert still_there["shipped"].stale_tracking_ref is False

    monkeypatch.setattr(status_cmd, "_remote_heads", lambda root: {"master"})
    gone = {r.name: r for r in status_cmd._branches_section(work).rows}
    assert gone["shipped"].stale_tracking_ref is True


def test_the_base_is_the_remote_default_branch_not_the_local_one(repo):
    """Step 4's loudest warning, pinned against a checkout that has not pulled.

    `ffmerged` landed on origin/master by an ordinary fast-forward, and the local master
    was then rewound behind it. Against `origin/master` the branch holds no patch of its
    own; against the local `master` it holds one. The second assertion is what stops
    this test from passing on either implementation.
    """
    work, _ = repo
    facts = {f.name: f for f in status_cmd._branch_facts(work, [], {"master"})}
    assert facts["ffmerged"].unshipped == 0

    against_local = status_cmd._git(work, "cherry", "master", "ffmerged") or ""
    assert sum(1 for ln in against_local.splitlines() if ln.startswith("+")) == 1, (
        "the fixture no longer distinguishes the two bases, so the assertion above "
        "would hold for an implementation that compares against the local branch"
    )


def test_gh_unreachable_makes_the_slot_absent_never_a_zero(repo, monkeypatch):
    """Rule 6 where this slot's sources fail independently.

    Without `gh` there is no PR state, and without PR state there is no join — every
    remaining signal is one of the three Step 4 says is wrong on its own. The slot must
    say so in words rather than count the branches it can still see.
    """
    work, _ = repo
    monkeypatch.setattr(status_cmd, "_gh_pull_requests", lambda root: None)
    monkeypatch.setattr(status_cmd, "_remote_heads", lambda root: {"master"})
    section = status_cmd._branches_section(work)
    assert isinstance(section.measurement, Absent)
    assert "gh" in say(section.measurement.reason)
    assert section.verdict == "unknown"


def test_ls_remote_unreachable_still_measures_but_admits_the_gap(repo, monkeypatch):
    """A missing remote view is not a missing join: the branch/PR verdicts stand, and
    only the tracking-ref half goes unknown. Collapsing the whole slot would throw away
    four working signals because a fifth was unavailable."""
    work, shipped_head = repo
    prs = [("shipped", PullRequest(number=1, state="MERGED", head_oid=shipped_head))]
    monkeypatch.setattr(status_cmd, "_gh_pull_requests", lambda root: prs)
    monkeypatch.setattr(status_cmd, "_remote_heads", lambda root: None)
    section = status_cmd._branches_section(work)
    assert isinstance(section.measurement, Count)
    rows = {r.name: r for r in section.rows}
    assert rows["shipped"].disposition == "shipped"
    assert rows["shipped"].stale_tracking_ref is None
    # Not `"ls-remote" in proof`: that substring is in the command line this proof
    # always names, so the assertion held whether or not the gap was admitted. The
    # clause is the thing the test's own name promises.
    assert "ls-remote did not answer" in say(section.measurement.proof)


def test_the_count_is_branches_needing_action_over_all_of_them(repo, monkeypatch):
    work, shipped_head = repo
    prs = [
        ("shipped", PullRequest(number=1, state="MERGED", head_oid=shipped_head)),
        ("live", PullRequest(number=3, state="OPEN", head_oid="x")),
    ]
    monkeypatch.setattr(status_cmd, "_gh_pull_requests", lambda root: prs)
    monkeypatch.setattr(status_cmd, "_remote_heads", lambda root: {"master"})
    m = status_cmd._branches_section(work).measurement
    assert isinstance(m, Count)
    # shipped (residue) and beyond (unproposed) need action. `live` has an open PR, and
    # `ffmerged` — which DID land by another route — is minutes old, which is exactly the
    # row Step 4 tells you to keep: "minutes old = a worktree just created and not yet
    # written in". Age, not content, is what makes that row quiet, and the fixture's
    # commits are all seconds old by construction.
    assert (m.value, m.of) == (2, 4)


def test_a_directory_that_is_not_a_repository_is_absent_not_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(status_cmd, "_gh_pull_requests", lambda root: [])
    monkeypatch.setattr(status_cmd, "_remote_heads", lambda root: set())
    section = status_cmd._branches_section(tmp_path)
    assert isinstance(section.measurement, Absent)
    assert section.verdict == "unknown"
