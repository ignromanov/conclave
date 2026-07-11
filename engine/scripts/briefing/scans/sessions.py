"""scans/sessions.py — section 6: Last sessions (top 3 for advisor).

Port of briefing-build.sh lines 267-289.
Scans sessions_dir for files matching *-<advisor>-*.md,
sorts basenames descending, takes top 3, formats as markdown links.
"""
from __future__ import annotations

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(no prior sessions recorded)_"


def build(ctx: ScanCtx) -> str:
    """Return a markdown list of up to 3 most-recent session files.

    File naming: <date>-<advisor>-<slug>.md
    Sort: lexicographic descending on basename (date prefix → newest first).
    Format: - [<basename>](sessions/<basename>.md)
    """
    sess_dir = ctx.sessions_dir
    if not sess_dir.is_dir():
        return _PLACEHOLDER

    pattern = f"*-{ctx.advisor}-*.md"
    matches = list(sess_dir.glob(pattern))
    if not matches:
        return _PLACEHOLDER

    basenames = sorted([f.stem for f in matches], reverse=True)
    top3 = basenames[:3]

    lines = [f"- [{base}](sessions/{base}.md)" for base in top3]
    return "\n".join(lines)
