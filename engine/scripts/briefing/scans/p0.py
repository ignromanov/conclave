"""scans/p0.py — section 5: Global p0 blockers, assembled over the whole roster.

Port of briefing-build.sh lines 250-265, and no longer faithful to it on purpose: the
bash original read one advisor's gh-cache under a heading that said "Global", and the
port inherited both halves of that (GH#269). No live gh calls — the union is over
snapshots on disk, one per advisor, and it reports the ones it could not read.
"""
from __future__ import annotations

from briefing.scans import ScanCtx
from briefing.scans._gh_cache import captured_at
from briefing.scans.queue import collect as _queue_collect
from briefing.scans.queue import format_row, issue_identity, read_items
from enginelib.advisors import lifecycle_advisors

P0_LABEL = "p0"

#: Every cache on the roster was read and none of them held a p0. The unqualified
#: all-clear; it is a claim about the instance and only a fully-read roster earns it.
NO_BLOCKERS = "_(no global p0 blockers)_"

#: Read what there was, found nothing, but the roster has holes. Distinguished from
#: NO_BLOCKERS because "nobody is on fire" and "I could not ask everybody" are
#: different answers and the reader cannot tell them apart from a shared placeholder.
NONE_IN_READ = "_(no p0 in the caches that could be read)_"


def collect(ctx: ScanCtx) -> list[dict]:
    """This ADVISOR's p0 items, matched on the label.

    Deliberately still advisor-scoped while `build()` above it is not. One cache is one
    advisor's view and that is the honest unit for a seam; the instance-wide answer is
    the union of these, which `build()` assembles by walking the roster. Widening this
    read instead would leave the union with no way to say that one of the shards it
    merged was five days older than the rest.
    """
    return select(_queue_collect(ctx))


def select(items: list[dict]) -> list[dict]:
    """The p0 subset of already-read gh-cache items. Pure — no I/O, no cache path.

    Split out from `collect()` so a caller assembling the instance-wide union reads each
    cache once and filters twice, instead of re-reading every cache per section. The
    predicate lives here ALONE, and that is now load-bearing rather than tidy: `build()`
    kept a second, substring copy of "what counts as p0" (``"p0" in row`` over the
    joined ``#num | title | labels`` string), deferred on a measurement that said the
    two were indistinguishable on this instance on 2026-09-09. Re-measured 2026-09-20
    over all five live caches: substring 1, label 0. The single row the section rendered
    was GH#269 itself — labelled `p1`, matched on the "p0" in its title.
    """
    return [
        item
        for item in items
        if any(lbl.get("name") == P0_LABEL for lbl in item.get("labels", []))
    ]


def _gap(advisor: str) -> str:
    """One roster member whose snapshot was never taken, as an actionable line.

    A floor, not a count. `captured_at` returning None is the only thing that separates
    "this advisor has no open p0" from "nobody ever asked GitHub about this advisor",
    because `read_items` answers [] to both.
    """
    return (
        f"- _(no snapshot for {advisor} — this list is a floor, not the instance; "
        f"run: python -m engine lifecycle gh-fetch --advisor {advisor})_"
    )


def build(ctx: ScanCtx) -> str:
    """The instance's p0 blockers, deduped across the roster's gh-cache snapshots.

    The roster is `lifecycle_advisors`, NOT the contents of `gh_cache_dir`. Globbing the
    cache directory is the shorter way to find "whose caches exist" and it is the wrong
    instrument for the same reason #104 names: a roster read off the caches cannot
    produce a member it failed to find, so an advisor who was never snapshotted stops
    being representable and the union quietly shrinks to whoever ran gh-fetch — while
    still calling itself global.

    WHAT THIS SECTION CANNOT TELL YOU: how old the union is. It reports a snapshot that
    was never taken and says nothing about one taken five days ago — measured on this
    instance 2026-09-20, four caches were minutes old and forge-chro's was 121 hours
    old, and all five render here identically. A stale shard did answer, so it is not a
    gap; grading the union by its OLDEST member is `enginelib.status.reduce.Mosaic`,
    which `engine status` prints and a briefing section has no room for.
    """
    advisor = ctx.advisor
    roster = sorted(lifecycle_advisors(ctx.repo_root))

    # The reader is on the roster, or the roster was resolved against the wrong tree.
    # `known_advisors` is empty-safe by design: a missing `.claude/agents/` yields an
    # empty set, so a mis-resolved root degrades to {forge-chro} and this section
    # renders a confident all-clear over one cache — the exact defect, restored through
    # a different door and silent. The reading advisor is the one member guaranteed to
    # exist, which makes them a free self-confirming check on the resolution.
    if advisor is not None and advisor not in roster:
        return (
            f"- _(roster not resolvable from {ctx.repo_root.name}/ — {advisor} is not on "
            f"it, so this section cannot be instance-wide; found: "
            f"{', '.join(roster) or 'nobody'})_"
        )

    rows: list[str] = []
    gaps: list[str] = []
    seen: set[str] = set()

    for member in roster:
        cache_path = ctx.gh_cache_dir / f"{member}.md"
        if captured_at(cache_path) is None:
            # Read the stamp, not the items: `read_items` returns [] for a missing
            # cache and for an empty one alike, so asking it first loses the difference
            # this branch exists to keep.
            gaps.append(_gap(member))
            continue
        for item in select(read_items(cache_path, advisor=member)):
            # Cache membership is an `advisor:` label query and label sets are not
            # exclusive, so one issue can sit in two caches legitimately. The number
            # alone is not an identity here — this instance runs two repos.
            identity = issue_identity(item)
            if identity in seen:
                continue
            seen.add(identity)
            row = format_row(item)
            if row:
                rows.append(f"- {row}")

    if not rows and not gaps:
        return NO_BLOCKERS
    if not rows:
        return "\n".join([NONE_IN_READ, "", *gaps])
    return "\n".join(rows + gaps)
