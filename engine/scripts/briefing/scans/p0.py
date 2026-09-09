"""scans/p0.py — section 5: Global p0 blockers (gh-cache filtered).

Port of briefing-build.sh lines 250-265.
Filters gh-cache rows to those containing 'p0' (substring match —
mirrors bash ``| grep 'p0'``).
No live gh calls.
"""
from __future__ import annotations

from briefing.scans import ScanCtx
from briefing.scans._gh_cache import read_gh_cache
from briefing.scans.queue import collect as _queue_collect

P0_LABEL = "p0"


def collect(ctx: ScanCtx) -> list[dict]:
    """This advisor's p0 items, matched on the LABEL.

    `build()` below keeps the bash port's predicate — ``"p0" in row`` over the joined
    ``#num | title | labels`` string — which also matches an issue whose *title*
    contains "p0". Measured on this instance 2026-09-09: substring 0, label 0, so
    the two definitions are indistinguishable here today and `build()` is left
    exactly as it was. It is left as it was for a second and better reason: the
    golden briefing net (plan 057 T4) is not built yet, and until it is, no change
    to a `build()` has an instrument that would catch it going wrong.

    This seam takes the label because it returns structured items, where the label
    list is present as data and there is no joined string to substring-match.

    Advisor-scoped by construction — the cache path is keyed by advisor. Making
    "global p0 blockers" actually global is the CALLER's job, over the whole roster;
    that this section's own title has claimed global while reading one cache since
    it was ported is the executed defect in plan 057 §2.
    """
    return select(_queue_collect(ctx))


def select(items: list[dict]) -> list[dict]:
    """The p0 subset of already-read gh-cache items. Pure — no I/O, no cache path.

    Split out from `collect()` so a caller assembling the instance-wide union reads
    each cache once and filters twice, instead of re-reading every cache per section.
    The predicate lives here alone; two copies of "what counts as p0" is how the
    substring/label divergence documented above came to exist in the first place.
    """
    return [
        item
        for item in items
        if any(lbl.get("name") == P0_LABEL for lbl in item.get("labels", []))
    ]


def build(ctx: ScanCtx) -> str:
    """Return markdown list of p0 issues from gh-cache.

    Uses substring 'p0' match to filter rows — exact bash parity.
    Placeholder: _(no global p0 blockers)_
    """
    cache_path = ctx.gh_cache_dir / f"{ctx.advisor}.md"
    # Stderr suppressed in bash (2>/dev/null) — we still get rows; stale
    # warnings are a side-effect but harmless for the filter pass.
    rows = read_gh_cache(cache_path, advisor=ctx.advisor)

    p0_rows = [row for row in rows if "p0" in row]
    if not p0_rows:
        return "_(no global p0 blockers)_"

    lines = [f"- {row}" for row in p0_rows if row.strip()]
    if not lines:
        return "_(no global p0 blockers)_"
    return "\n".join(lines)
