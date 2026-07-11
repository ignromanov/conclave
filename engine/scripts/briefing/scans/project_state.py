"""scans/project_state.py — section 2: Project state (progress-summary.md).

Port of briefing-build.sh lines 188-205.
Reads progress-summary.md, skips top-level headings and blockquotes,
trims leading blank lines, then truncates to 20 lines (head -n 20).
"""
from __future__ import annotations

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(progress-summary.md missing)_"


def build(ctx: ScanCtx) -> str:
    """Return the first 20 meaningful lines from progress-summary.md.

    Bash logic:
      awk '/^# / { next }  /^>/ { next }  { print }' progress-summary.md
        | awk 'NF{found=1} found'   # trim leading blanks
        | head -n 20
    """
    path = ctx.progress_path
    if not path.is_file():
        return _PLACEHOLDER

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=False)

    # Pass 1: drop top-level headings (^# ) and blockquote lines (^>).
    filtered: list[str] = []
    for line in lines:
        if line.startswith("# "):
            continue
        if line.startswith(">"):
            continue
        filtered.append(line)

    # Pass 2: trim leading blank lines (awk 'NF{found=1} found').
    found = False
    trimmed: list[str] = []
    for line in filtered:
        if line.strip():
            found = True
        if found:
            trimmed.append(line)

    # Pass 3: head -n 20.
    result_lines = trimmed[:20]
    return "\n".join(result_lines)
