"""scans/p0.py — section 5: Global p0 blockers (gh-cache filtered).

Port of briefing-build.sh lines 250-265.
Filters gh-cache rows to those containing 'p0' (substring match —
mirrors bash ``| grep 'p0'``).
No live gh calls.
"""
from __future__ import annotations

from briefing.scans import ScanCtx
from briefing.scans._gh_cache import read_gh_cache


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
