"""status/branches.py — the branch × PR-state join (plan 057 T9).

`/conclave:start` Step 4 specifies this join in bash and states its own limit: on
`unshipped>0 + merged` it declines to rule, because `git cherry` cannot tell "commits
landed after the merge" from "the squash hid every patch-id". Its instruction there is
"Read the log; do not guess."

These tests pin the join, Step 4's five rows first. Then they pin the two rows Step 4
does not have — the ones that make the projection worth building rather than printing
the bash again:

  * `beyond_merge`, the fourth signal. GitHub freezes a merged PR's `headRefOid` at
    what it merged, so `rev-list <head_oid>..<branch>` counts exactly the commits pushed
    afterwards. That decides Step 4's undecidable row without a patch-id heuristic.
  * `RemoteState`, measured on this instance 2026-09-14: `refs/remotes/origin/<b>` is a
    CACHE of the remote branch, and it outlives the branch. Without it the join calls
    today's incident "fully shipped, delete locally" while a resurrected branch sits on
    the server.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from enginelib.status.branches import (
    DORMANT_AFTER,
    BranchFact,
    PullRequest,
    classify,
    join,
    needs_action,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def fact(**kw) -> BranchFact:
    """A branch fact with everything measured and nothing interesting, by default."""
    base = dict(
        name="feature",
        unshipped=0,
        last_commit=NOW - timedelta(hours=1),
        has_worktree=False,
        prs=(),
        beyond_merge=None,
        remote=None,
    )
    base.update(kw)
    return BranchFact(**base)


def merged(number: int = 1, head_oid: str = "aaa") -> PullRequest:
    return PullRequest(number=number, state="MERGED", head_oid=head_oid)


def open_pr(number: int = 2, head_oid: str = "bbb") -> PullRequest:
    return PullRequest(number=number, state="OPEN", head_oid=head_oid)


# --------------------------------------------------------------------------
# Step 4's five rows, in its own order
# --------------------------------------------------------------------------


def test_no_patches_and_a_merged_pr_is_fully_shipped():
    row = classify(fact(unshipped=0, prs=(merged(),), beyond_merge=0), NOW)
    assert row.disposition == "shipped"


def test_open_pr_is_live_work_whatever_the_patch_count():
    """Step 4 pairs `open` with `>0`, but an open PR is in flight at any count.

    The row Step 4 does not write is `0 + open`, which happens whenever a PR's work
    reaches the base by another route while the PR is still open. Calling that one
    removable would close a PR's branch under it.
    """
    for unshipped in (0, 3):
        row = classify(fact(unshipped=unshipped, prs=(open_pr(),)), NOW)
        assert row.disposition == "in_flight", f"unshipped={unshipped}"


def test_own_patches_and_no_pr_is_unproposed():
    row = classify(fact(unshipped=2, prs=()), NOW)
    assert row.disposition == "unproposed"


def test_no_patches_no_pr_splits_on_age_not_on_content():
    """Step 4: "minutes old = keep, days old = stale" — the age column IS the verdict."""
    young = classify(fact(last_commit=NOW - timedelta(minutes=5)), NOW)
    old = classify(fact(last_commit=NOW - DORMANT_AFTER - timedelta(seconds=1)), NOW)
    assert young.disposition == "fresh_start"
    assert old.disposition == "landed_elsewhere"


def test_a_closed_unmerged_pr_does_not_count_as_a_pr_but_is_named():
    """CLOSED is not MERGED. Step 4's table has no row for it; the safe reading is
    "no PR" for the verdict, because nothing shipped — but the row must still say a
    PR existed, or the operator re-opens the same question next week."""
    row = classify(fact(unshipped=1, prs=(PullRequest(number=9, state="CLOSED", head_oid="c"),)), NOW)
    assert row.disposition == "unproposed"
    assert "#9" in row.reason


# --------------------------------------------------------------------------
# The row Step 4 declines to rule on
# --------------------------------------------------------------------------


def test_cherry_blindness_over_a_squash_resolves_to_shipped():
    """`unshipped>0 + merged + nothing after the merge` is the N>1 squash, decided.

    This is the entire reason the module exists. Step 4 must answer "Look before
    removing" here because it has three signals; with `beyond_merge` the answer is
    known, and it is the opposite of what `git cherry` alone implies.
    """
    row = classify(fact(unshipped=7, prs=(merged(),), beyond_merge=0), NOW)
    assert row.disposition == "shipped"
    assert "7" in row.reason and "squash" in row.reason.lower()


def test_real_commits_after_the_merge_are_their_own_disposition():
    row = classify(fact(unshipped=7, prs=(merged(),), beyond_merge=3), NOW)
    assert row.disposition == "beyond_merge"
    assert "3" in row.reason


def test_an_unmeasured_fourth_signal_falls_back_to_step_4s_own_verdict():
    """`beyond_merge=None` means the signal could not be taken — no oid, git failed,
    gh offline. The join must then degrade to Step 4's honest ambiguity, not to a
    guess in either direction: rule 6 forbids rendering "could not measure" as a
    decided value, and this is that rule one level below the printer."""
    row = classify(fact(unshipped=7, prs=(merged(),), beyond_merge=None), NOW)
    assert row.disposition == "inspect"


def test_a_merged_pr_with_no_patches_needs_no_fourth_signal():
    """Nothing to disambiguate: cherry and the PR already agree."""
    row = classify(fact(unshipped=0, prs=(merged(),), beyond_merge=None), NOW)
    assert row.disposition == "shipped"


# --------------------------------------------------------------------------
# The remote is not the remote-tracking ref (measured 2026-09-14)
# --------------------------------------------------------------------------


def test_a_ghost_tracking_ref_is_flagged_and_cleaned_by_pruning():
    """Today's incident, as a test.

    `refs/remotes/origin/057-engine-status-core` existed locally; the branch on the
    server did not, because the squash-merge deleted it. `git status` read the ghost as
    "the branch exists and you are 8 ahead", and the push that followed recreated the
    branch on the server. The row must say the LOCAL cache is wrong — and the remedy is
    a prune, never a remote delete.
    """
    row = classify(fact(unshipped=0, prs=(merged(),), beyond_merge=0, remote="gone"), NOW)
    assert row.disposition == "shipped"
    assert row.stale_tracking_ref is True
    assert "prune" in row.cleanup
    assert "push origin --delete" not in row.cleanup


def test_a_shipped_branch_still_on_the_server_must_be_deleted_there_too():
    """The opposite direction, and the one a local-only join gets silently wrong: the
    PR merged but the head branch survived on the remote, so deleting it locally leaves
    a branch that reads as live work to everyone else in the repository."""
    row = classify(fact(unshipped=0, prs=(merged(),), beyond_merge=0, remote="present"), NOW)
    assert row.stale_tracking_ref is False
    assert "push origin --delete" in row.cleanup


def test_remote_state_unmeasured_is_not_remote_state_clean():
    """`remote=None` is "did not look". It must not render as "looked, fine"."""
    row = classify(fact(unshipped=0, prs=(merged(),), beyond_merge=0, remote=None), NOW)
    assert row.stale_tracking_ref is None


# --------------------------------------------------------------------------
# Cleanup mechanics — Step 4's "second join"
# --------------------------------------------------------------------------


def test_a_worktree_row_says_remove_the_worktree_first():
    bare = classify(fact(unshipped=0, prs=(merged(),), beyond_merge=0, has_worktree=False), NOW)
    wt = classify(fact(unshipped=0, prs=(merged(),), beyond_merge=0, has_worktree=True), NOW)
    assert "worktree remove" not in bare.cleanup
    assert "worktree remove" in wt.cleanup


def test_the_delete_is_capital_d_because_minus_d_refuses_on_a_squash():
    """Step 4 is explicit that `-d` refuses forever on a squash-merged branch, which is
    why such branches accumulate. A cleanup line printing `-d` would be advice that
    cannot be followed."""
    row = classify(fact(unshipped=0, prs=(merged(),), beyond_merge=0), NOW)
    assert "branch -D" in row.cleanup
    assert "branch -d " not in row.cleanup


def test_live_work_is_never_given_a_cleanup_line():
    assert classify(fact(prs=(open_pr(),)), NOW).cleanup == ""


# --------------------------------------------------------------------------
# The join over many branches
# --------------------------------------------------------------------------


def test_join_preserves_every_branch_and_names_each_once():
    facts = [fact(name=n) for n in ("a", "b", "c")]
    rows = join(facts, NOW)
    assert [r.name for r in rows] == ["a", "b", "c"]


def test_needs_action_excludes_live_and_brand_new_work_only():
    rows = join(
        [
            fact(name="live", prs=(open_pr(),)),
            fact(name="new", last_commit=NOW - timedelta(minutes=2)),
            fact(name="done", unshipped=0, prs=(merged(),), beyond_merge=0),
            fact(name="risky", unshipped=1, prs=(merged(),), beyond_merge=2),
            fact(name="orphan", unshipped=4),
        ],
        NOW,
    )
    assert {r.name for r in needs_action(rows)} == {"done", "risky", "orphan"}


def test_every_row_carries_a_reason_a_human_can_act_on():
    """Rule 5/6 one level down: no disposition is allowed to be a bare label."""
    rows = join(
        [
            fact(name="live", prs=(open_pr(),)),
            fact(name="new", last_commit=NOW - timedelta(minutes=2)),
            fact(name="done", prs=(merged(),), beyond_merge=0),
            fact(name="risky", unshipped=1, prs=(merged(),), beyond_merge=2),
            fact(name="unsure", unshipped=1, prs=(merged(),), beyond_merge=None),
            fact(name="orphan", unshipped=4),
            fact(name="old", last_commit=NOW - timedelta(days=30)),
        ],
        NOW,
    )
    seen = {r.disposition for r in rows}
    assert len(seen) == 7, f"a disposition is untested by this fixture: {seen}"
    for row in rows:
        assert row.reason.strip(), f"{row.name} ({row.disposition}) has no reason"


# --------------------------------------------------------------------------
# Construction refuses the states that would render as a lie
# --------------------------------------------------------------------------


def test_a_negative_count_is_rejected_at_construction():
    with pytest.raises(ValueError):
        fact(unshipped=-1)
    with pytest.raises(ValueError):
        fact(beyond_merge=-1)


def test_beyond_merge_without_a_merged_pr_is_a_contradiction():
    """`beyond_merge` is measured from a merged PR's frozen head oid. A value here with
    no merged PR means the caller measured it against something else, and the join
    would then rule on a signal that does not mean what its name says."""
    with pytest.raises(ValueError):
        fact(prs=(open_pr(),), beyond_merge=0)


def test_a_branch_that_was_never_pushed_needs_no_remote_step_and_is_no_ghost():
    """The third remote state, and the reason a boolean was not enough: "no branch on
    the server" is true here and true for a ghost, and the two need opposite advice."""
    row = classify(fact(unshipped=0, prs=(merged(),), beyond_merge=0, remote="never_pushed"), NOW)
    assert row.stale_tracking_ref is False
    assert "origin" not in row.cleanup
    assert "prune" not in row.cleanup


def test_an_unmeasured_patch_count_cannot_rule_on_an_unproposed_branch():
    """`git cherry` fails outright on a branch sharing no history with the base — this
    repository has such branches by construction, since its history was recut (see
    `doctor._orphan_branches`). `unshipped=None` is that failure, and it must not read
    as "no patches of its own", which is the difference between "stale, delete it" and
    "nobody has looked at this work"."""
    row = classify(fact(unshipped=None, prs=()), NOW)
    assert row.disposition == "inspect"
    assert "cherry" in row.reason


def test_an_unmeasured_patch_count_is_still_shipped_when_the_pr_settles_it():
    """The fourth signal does not need the first one: if the PR merged and nothing
    landed after it, the patch count has nothing left to contribute."""
    row = classify(fact(unshipped=None, prs=(merged(),), beyond_merge=0), NOW)
    assert row.disposition == "shipped"
