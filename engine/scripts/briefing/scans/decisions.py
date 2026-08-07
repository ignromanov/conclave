"""scans/decisions.py — section 3: Recent cross-cutting decisions (top 5).

Port of briefing-build.sh lines 207-231.
Sources:
  1. decisions_dir (agent-memory/advisors/decisions/) — files matching
     *-<advisor>-*.md (advisor-specific).
  2. ops/decisions/ — all *.md files (cross-cutting Y-statements, no
     advisor name in path).  Stems are merged into the same sorted pool.

Sort: lexicographic descending on basename (date prefix → newest first).
Top 5 across both sources.
"""
from __future__ import annotations

from briefing.scans import ScanCtx
from enginelib.advisors import files_for_advisor

_PLACEHOLDER = "_(no decisions recorded yet)_"


def build(ctx: ScanCtx) -> str:
    """Return a markdown list of up to 5 most-recent decision files.

    Merges advisor decisions (agent-memory/advisors/decisions/) and
    cross-cutting Y-statements (ops/decisions/).  Both sets are sorted
    together lexicographically descending so date-prefixed filenames
    surface the newest entries first.

    Format: - [<stem>](decisions/<stem>.md)
    """
    stems: list[str] = []

    # 1. Advisor-specific decisions.
    dec_dir = ctx.decisions_dir
    if dec_dir.is_dir():
        stems.extend(f.stem for f in files_for_advisor(dec_dir, ctx.advisor, field="by"))

    # 2. Cross-cutting Y-statements from ops/decisions/.
    ops_dec_dir = ctx.repo_root / "ops" / "decisions"
    if ops_dec_dir.is_dir():
        stems.extend(
            f.stem
            for f in ops_dec_dir.glob("*.md")
            if f.stem not in {"INDEX", "README", "template"}
        )

    if not stems:
        return _PLACEHOLDER

    # Sort descending by basename (mirrors bash `sort -r`); drop dups.
    top5 = sorted(set(stems), reverse=True)[:5]

    lines = [f"- [{base}](decisions/{base}.md)" for base in top5]
    return "\n".join(lines)
