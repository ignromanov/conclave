"""scans/roadmap.py — section #6: Domain/roadmap.

Reads spec frontmatter ``status`` + ``title`` + ``milestone`` for all
advisor-owned specs and renders a concise roadmap view: which version
target is next, which specs are in-progress / proposed / done.

Scan logic:
  1. Walk ops/specs/###-*/spec.md; filter by ctx.advisor.
  2. Group by ``milestone`` (or "untracked"); sort by spec id.
  3. Surface in-progress specs first, then proposed, then done/archived.

Empty-state: _(no roadmap entries for advisor)_
"""
from __future__ import annotations

import re
from pathlib import Path

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(no roadmap entries for advisor)_"

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Status ordering: lower = higher priority in display.
_STATUS_ORDER = {
    "in_progress": 0,
    "in-progress": 0,
    "approved": 1,
    "proposed": 2,
    "done": 3,
    "archived": 4,
    "cancelled": 5,
}


def build(ctx: ScanCtx) -> str:
    """Return roadmap markdown for advisor-owned specs."""
    specs_root = ctx.repo_root / "ops" / "specs"
    if not specs_root.is_dir():
        return _PLACEHOLDER

    entries: list[dict[str, str]] = []
    for spec_path in sorted(specs_root.glob("*/spec.md")):
        entry = _extract_entry(spec_path, ctx.advisor)
        if entry is not None:
            entries.append(entry)

    if not entries:
        return _PLACEHOLDER

    # Sort: by status priority, then by spec id.
    entries.sort(key=lambda e: (_STATUS_ORDER.get(e["status"], 99), e["id"]))

    lines: list[str] = []
    for e in entries:
        milestone = f" · {e['milestone']}" if e["milestone"] else ""
        lines.append(f"- [{e['status']}] **{e['id']}** {e['title']}{milestone}")

    return "\n".join(lines)


def _extract_entry(spec_path: Path, advisor: str) -> dict[str, str] | None:
    """Return dict(id, title, status, milestone) if spec belongs to advisor."""
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm = _parse_frontmatter(text)
    if not (fm.get("advisor") == advisor or fm.get("owner_suggestion") == advisor):
        return None

    return {
        "id": str(fm.get("id") or fm.get("spec_id") or spec_path.parent.name),
        "title": fm.get("title") or "untitled",
        "status": fm.get("status") or "unknown",
        "milestone": fm.get("milestone") or fm.get("phase") or "",
    }


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Return flat dict of frontmatter key→value (best-effort, string only)."""
    m = _FM_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            out[key.strip()] = val.strip().strip('"')
    return out
