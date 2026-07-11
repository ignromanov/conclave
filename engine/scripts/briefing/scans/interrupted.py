"""scans/interrupted.py — section: Interrupted work (Phase 2, #10).

Renders resume-prompts from ops/handoffs/ that have ``status: open`` (or
any non-terminal status), sorted by mtime descending (most recently touched
first). Shows path, mtime, and the status field.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import frontmatter

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(no interrupted work / open resume-prompts found)_"

# Terminal statuses — files with these are excluded.
_TERMINAL = {"complete", "completed", "done", "archived", "closed", "superseded"}

_MAX_ITEMS = 5


def build(ctx: ScanCtx) -> str:
    """Return markdown list of open resume-prompts sorted by mtime."""
    handoffs_dir = ctx.repo_root / "ops" / "handoffs"
    items = _collect_open_handoffs(handoffs_dir)

    if not items:
        return _PLACEHOLDER

    lines: list[str] = []
    for path, mtime_str, status in items[:_MAX_ITEMS]:
        rel = path.relative_to(ctx.repo_root)
        lines.append(f"- [{path.name}]({rel}) — status: `{status}` — modified: {mtime_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_open_handoffs(
    handoffs_dir: Path,
) -> list[tuple[Path, str, str]]:
    """Return [(path, mtime_iso, status)] for non-terminal handoff .md files.

    Sorted by mtime descending (most recently modified first).
    """
    if not handoffs_dir.is_dir():
        return []

    candidates: list[tuple[float, Path, str]] = []

    for md in handoffs_dir.glob("*.md"):
        if md.name.startswith("_") or md.name == "INDEX.md":
            continue
        try:
            post = frontmatter.load(str(md))
        except Exception:
            continue

        status = str(post.metadata.get("status", "open")).lower()
        if status in _TERMINAL:
            continue

        try:
            mtime = os.path.getmtime(md)
        except OSError:
            continue

        candidates.append((mtime, md, status))

    candidates.sort(key=lambda t: t[0], reverse=True)

    results: list[tuple[Path, str, str]] = []
    for mtime, path, status in candidates:
        dt = datetime.fromtimestamp(mtime, tz=UTC)
        mtime_str = dt.strftime("%Y-%m-%d %H:%M UTC")
        results.append((path, mtime_str, status))

    return results
