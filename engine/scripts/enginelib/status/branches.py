"""status/branches.py — the branch × PR-state join. I/O-free, pure.

`/conclave:start` Step 4 specifies this join in bash and states, in the table itself,
where it runs out of evidence:

    | >0 | merged | **Look before removing.** Either commits landed *after* the merge
    | (real work — keep), or `git cherry` cannot see the squash [...] Read the log; do
    | not guess.

That row is why re-printing the bash would be worthless. Step 4 has three signals and
none of them separates "work pushed after the merge" from "the squash hid every
patch-id", so it correctly refuses to rule and hands the question back to a human who,
on the evidence of this instance's eleven stale worktrees, does not answer it.

This module adds the fourth signal that decides it. **GitHub freezes a merged PR's
`headRefOid` at the commit it merged** — measured on this instance 2026-09-14: PR #263
still reported `7ab2433` after `8eeb6b6` was pushed to its branch. So

    beyond_merge = git rev-list --count <pr.head_oid>..<branch>

counts exactly the commits that arrived after the merge, with no patch-id heuristic and
no blindness to the size of the squash. `unshipped>0 & beyond_merge==0` is cherry losing
a squash; `beyond_merge>0` is real work. Step 4's undecidable row becomes two decided
ones, and its verdict survives — as `inspect` — for the case where the fourth signal
could not be taken at all.

The fifth signal comes from the same day and is not in Step 4 either:
`refs/remotes/origin/<branch>` is a **cache** of the remote branch and outlives it. Step 4
hides this by running `git fetch --prune` first; a read-model must not, because a
projection that mutates refs to measure them is not a read. `RemoteState` is therefore
taken from `git ls-remote` — the read, where `fetch --prune` is the write — and without
it this join calls a resurrected remote branch "fully shipped, delete it locally".

`RemoteState` has three values and not two because the obvious boolean conflates the
same pair rule 6 is about: a branch that was never pushed and a branch whose remote head
vanished both answer "no" to *is there a remote branch?*, and they need opposite advice —
nothing at all, versus prune your ghost ref. `None` on top of those three is the fourth
state, "the remote was not consulted", which is what an offline run reports.

Layering: this module performs no I/O and imports nothing from `briefing/` (GH#106). Every
signal above is measured by the adapter and passed in; what lives here is only the part
three printers must not each re-derive.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from enginelib.status.model import Severity, Verdict
from enginelib.status.reduce import worst_severity, worst_verdict

# Step 4's tie-breaker for the `no patches, no PR` row: "minutes old = a worktree just
# created and not yet written in (keep); days old = work that landed by some other route
# (stale)". One day is the smallest boundary that keeps a whole working session on the
# "keep" side of it.
DORMANT_AFTER = timedelta(days=1)

PRState = Literal["OPEN", "MERGED", "CLOSED"]

RemoteState = Literal[
    "present",       # the server still holds this branch
    "gone",          # the local refs/remotes cache holds it, the server does not
    "never_pushed",  # no tracking ref and no remote branch: purely local work
]

Disposition = Literal[
    "in_flight",         # an open PR — Step 4: "Live work in flight. Leave it."
    "shipped",           # Step 4: "Fully shipped."
    "beyond_merge",      # merged, and commits arrived afterwards — decided, not guessed
    "inspect",           # Step 4: "Look before removing." — kept for the unmeasured case
    "unproposed",        # Step 4: "Unshipped and unproposed."
    "landed_elsewhere",  # no patches of its own, no PR, dormant
    "fresh_start",       # no patches of its own, no PR, minutes old
]

# Dispositions the operator can leave alone. Everything else is residue, risk, or a
# question. `fresh_start` is here because Step 4 puts it there explicitly ("keep"), and
# `in_flight` because an open PR is the one state this projection must never disturb.
_QUIET: frozenset[str] = frozenset({"in_flight", "fresh_start"})

_VERDICT_BY_DISPOSITION: dict[Disposition, Verdict] = {
    # Rule 2 ranks uncertainty above known-bad, and `inspect` IS uncertainty: the
    # fourth signal was not taken, so the row could be either of two opposite things.
    "inspect": "unknown",
    # Commits sitting on top of a merged PR are the one shape that loses work if the
    # branch is cleaned up on the strength of "its PR merged".
    "beyond_merge": "stale_error",
    "shipped": "stale_warn",
    "unproposed": "stale_warn",
    "landed_elsewhere": "stale_warn",
    "in_flight": "fresh",
    "fresh_start": "fresh",
}

# The same judgments, on the axis they were always about. Every entry above is a
# statement about what a branch IS — residue, risk, or a question — and not one of them
# is about how old a reading is; the table borrowed the freshness vocabulary because
# until rules 7a/7b there was only one enum to borrow. Reading them off `Verdict` is how
# a branch slot's real problem ended up sharing a glyph column with a stale gh snapshot.
#
# `inspect` maps to `warn` and not to a fourth member: uncertainty is an ORDERING fact
# (rule 2 ranks it first, and `_VERDICT_BY_DISPOSITION` above still carries it there),
# while the glyph answers "must a reader act on this?" — and for `inspect` the answer is
# yes, because the row could be either of two opposite things.
_SEVERITY_BY_DISPOSITION: dict[Disposition, Severity] = {
    "inspect": "warn",
    "beyond_merge": "error",
    "shipped": "warn",
    "unproposed": "warn",
    "landed_elsewhere": "warn",
    "in_flight": "ok",
    "fresh_start": "ok",
}


@dataclass(frozen=True)
class PullRequest:
    """One PR as the join needs it: what it is now, and what it merged.

    `head_oid` is load-bearing only for `state == "MERGED"`, where GitHub has frozen it
    at the merged commit. For an open PR it tracks the branch and means nothing here.
    """

    number: int
    state: PRState
    head_oid: str


@dataclass(frozen=True)
class BranchFact:
    """Everything measured about one local branch, before any of it is interpreted.

    Two fields are `| None` on purpose, and the reason is rule 6 one level below the
    printer: `None` is "this signal was not taken", which is a different fact from any
    value it could have had. A caller that cannot reach `gh` passes `beyond_merge=None`
    and gets Step 4's honest ambiguity; a caller that passes `0` is asserting it looked.
    """

    name: str
    unshipped: int | None
    last_commit: datetime
    has_worktree: bool
    prs: tuple[PullRequest, ...] = ()
    beyond_merge: int | None = None
    remote: RemoteState | None = None

    @property
    def tracking_ref_is_stale(self) -> bool | None:
        """Is this repository's own view of the remote wrong? `None` when unmeasured.

        Derived rather than stored: `never_pushed` answers "no" here for a reason that
        has nothing to do with `present` answering "no", and a caller that stored one
        boolean would have had to remember which.
        """
        if self.remote is None:
            return None
        return self.remote == "gone"

    def __post_init__(self) -> None:
        if self.unshipped is not None and self.unshipped < 0:
            raise ValueError(f"unshipped is a cardinality, got {self.unshipped}")
        if self.beyond_merge is not None:
            if self.beyond_merge < 0:
                raise ValueError(f"beyond_merge is a cardinality, got {self.beyond_merge}")
            if self.merged_pr is None:
                raise ValueError(
                    f"{self.name}: beyond_merge={self.beyond_merge} with no merged PR. "
                    "The signal is defined as rev-list <merged PR head oid>..<branch>; "
                    "a value measured against anything else does not mean what the join "
                    "reads it to mean."
                )

    @property
    def merged_pr(self) -> PullRequest | None:
        """The merged PR, if one exists. Several would mean the branch shipped twice;
        the first by number is the one whose head oid the join uses."""
        for pr in sorted(self.prs, key=lambda p: p.number):
            if pr.state == "MERGED":
                return pr
        return None

    @property
    def open_prs(self) -> tuple[PullRequest, ...]:
        return tuple(p for p in self.prs if p.state == "OPEN")


@dataclass(frozen=True)
class BranchRow:
    """One branch, ruled on: what it is, why, and what cleaning it up actually takes."""

    name: str
    disposition: Disposition
    reason: str
    cleanup: str = ""
    stale_tracking_ref: bool | None = None

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError(
                f"{self.name}: a disposition without a reason is a bare label, which is "
                "the rule-5 defect this whole projection exists to retire"
            )


def _pr_names(prs: Sequence[PullRequest]) -> str:
    return ", ".join(f"#{p.number}:{p.state}" for p in sorted(prs, key=lambda p: p.number))


def _cleanup(fact: BranchFact) -> str:
    """The commands this row actually needs, in the order they must run.

    `-D` and not `-d`: Step 4 is explicit that `-d` refuses forever on a squash-merged
    branch, which is precisely why such branches accumulate. The capital D is licensed
    by the join having been done, not by impatience.
    """
    steps: list[str] = []
    if fact.has_worktree:
        steps.append(f"git worktree remove <path> && git branch -D {fact.name}")
    else:
        steps.append(f"git branch -D {fact.name}")

    # The remote half, and it points opposite ways. `present` means the server still
    # holds the branch, so a local-only delete leaves something that reads as live work
    # to every other clone. `gone` means the opposite: the server dropped it and the
    # local tracking ref is a ghost, whose remedy is a prune — a `push --delete` there
    # would ask the server to delete what it does not have, and a push aimed at that
    # name is what RESURRECTS it (measured 2026-09-14). `never_pushed` and `None` add
    # no remote step: there is nothing there, or nobody looked.
    if fact.remote == "present":
        steps.append(f"git push origin --delete {fact.name}")
    elif fact.remote == "gone":
        steps.append("git fetch --prune origin")
    return " ; ".join(steps)


def classify(fact: BranchFact, now: datetime) -> BranchRow:
    """Rule on one branch. Step 4's table, plus the two rows its signals cannot reach."""
    if fact.open_prs:
        return BranchRow(
            name=fact.name,
            disposition="in_flight",
            reason=f"открытый PR {_pr_names(fact.open_prs)} — работа в полёте",
            stale_tracking_ref=fact.tracking_ref_is_stale,
        )

    merged = fact.merged_pr
    if merged is not None:
        if fact.beyond_merge is None:
            # The deciding signal is missing, so fall back to what Step 4 itself can
            # say — and Step 4 needs the patch count to say even that. Nested rather
            # than two flat conditions because the second one's safety depends on the
            # first one having returned: mypy could not see that across sibling ifs,
            # which is a fair complaint about a reader, not only about a checker.
            if fact.unshipped is None:
                return BranchRow(
                    name=fact.name,
                    disposition="inspect",
                    reason=(
                        f"PR #{merged.number} смёржен, но ни git cherry, ни rev-list от "
                        "head_oid не отработали — судить не по чему"
                    ),
                    stale_tracking_ref=fact.tracking_ref_is_stale,
                )
            if fact.unshipped > 0:
                return BranchRow(
                    name=fact.name,
                    disposition="inspect",
                    reason=(
                        f"PR #{merged.number} смёржен, но git cherry насчитал "
                        f"{fact.unshipped} своих патчей, а четвёртый сигнал (rev-list от "
                        "head_oid PR) не снят — это либо работа поверх мёржа, либо "
                        "слепота cherry к squash"
                    ),
                    stale_tracking_ref=fact.tracking_ref_is_stale,
                )
        if fact.beyond_merge:
            return BranchRow(
                name=fact.name,
                disposition="beyond_merge",
                reason=(
                    f"PR #{merged.number} смёржен, и после него на ветку легло "
                    f"{fact.beyond_merge} коммитов — это работа, а не остаток"
                ),
                stale_tracking_ref=fact.tracking_ref_is_stale,
            )
        hidden = (
            f"; git cherry показывал {fact.unshipped} — это squash, а не неотправленная работа"
            if fact.unshipped
            else ""
        )
        return BranchRow(
            name=fact.name,
            disposition="shipped",
            reason=f"PR #{merged.number} смёржен, после него на ветку ничего не легло{hidden}",
            cleanup=_cleanup(fact),
            stale_tracking_ref=fact.tracking_ref_is_stale,
        )

    closed = f" (был PR {_pr_names(fact.prs)})" if fact.prs else ""
    if fact.unshipped is None:
        # No PR to settle the question and no patch count to ask: every remaining
        # signal is about age, and age alone cannot tell "unproposed work" from
        # "residue". Saying so is the only honest row.
        return BranchRow(
            name=fact.name,
            disposition="inspect",
            reason=f"git cherry не отработал (расходящаяся история?), PR нет{closed}",
            stale_tracking_ref=fact.tracking_ref_is_stale,
        )
    if fact.unshipped:
        return BranchRow(
            name=fact.name,
            disposition="unproposed",
            reason=f"{fact.unshipped} своих патчей и ни одного открытого PR{closed}",
            cleanup=_cleanup(fact),
            stale_tracking_ref=fact.tracking_ref_is_stale,
        )

    if now - fact.last_commit >= DORMANT_AFTER:
        return BranchRow(
            name=fact.name,
            disposition="landed_elsewhere",
            reason=(
                f"своих патчей нет, PR нет{closed}, последний коммит "
                f"{(now - fact.last_commit).days} дн. назад — работа ушла другим путём"
            ),
            cleanup=_cleanup(fact),
            stale_tracking_ref=fact.tracking_ref_is_stale,
        )

    return BranchRow(
        name=fact.name,
        disposition="fresh_start",
        reason=f"своих патчей нет, PR нет{closed}, ветка создана только что",
        stale_tracking_ref=fact.tracking_ref_is_stale,
    )


def join(facts: Iterable[BranchFact], now: datetime) -> list[BranchRow]:
    """Every branch, ruled on, in the order given. Nothing is dropped for being quiet —
    rule 3 states success rather than implying it, and a branch omitted for looking fine
    is indistinguishable from one the join never saw."""
    return [classify(f, now) for f in facts]


def needs_action(rows: Iterable[BranchRow]) -> list[BranchRow]:
    """The rows an operator must do something about."""
    return [r for r in rows if r.disposition not in _QUIET]


def section_verdict(rows: Sequence[BranchRow]) -> Verdict:
    """One verdict over the whole slot, worst-first.

    Combined through `worst_verdict` rather than by hand so the `unknown`-outranks-bad
    ordering is the one rule 2 fixed, in the one place it is written down. An empty
    branch list is `fresh`: no branches is a measured state, not an unmeasured one — the
    caller renders `Absent` when it could not look at all.
    """
    if not rows:
        return "fresh"
    verdicts = [_VERDICT_BY_DISPOSITION[r.disposition] for r in rows]
    if any(r.stale_tracking_ref for r in rows):
        # A tracking ref pointing at a branch that no longer exists is not a staleness
        # gradient, it is a wrong fact in the reader's own repository — and one that a
        # push silently acts on.
        verdicts.append("stale_error")
    return worst_verdict(*verdicts)


def section_severity(rows: Sequence[BranchRow]) -> Severity:
    """What the slot says about the branches themselves — the glyph's input (rule 7a).

    An empty branch list is `ok` and not `None`: this slot HAS a defensible threshold
    (a branch requiring action is by definition a deviation), so "we looked and there
    was nothing to act on" is a judgment, which is exactly what rule 3 wants stated.
    `None` is reserved for slots nobody has judged, and this is not one of them.

    A stale tracking ref outranks every disposition, for the reason the sibling above
    gives: it is not a gradient, it is a false fact in the reader's own repository.
    """
    if not rows:
        return "ok"
    severities = [_SEVERITY_BY_DISPOSITION[r.disposition] for r in rows]
    if any(r.stale_tracking_ref for r in rows):
        severities.append("error")
    return worst_severity(*severities) or "ok"
