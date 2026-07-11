"""scans/project_digest.py — section #12: Project digest.

Digests ``progress-summary.md`` into 3–5 dated bullets by extracting
the most recent entries from the **Recent** and **In Progress** lines.
The output is measurably smaller than the verbatim blob (that is the
point — token cut for the briefing budget).

Extraction heuristic:
  - Find the ``**Recent**:`` paragraph — split on ``, `` + spec-id prefix.
  - Take the first 3 entries (newest first in the file).
  - Append ``**In Progress**`` and ``**Next**`` one-liners if present.
  - Cap total bullets at 5.

Empty-state: _(progress-summary.md missing)_
"""
from __future__ import annotations

import re

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(progress-summary.md missing)_"

# Matches "NNN-slug" spec-id prefix used as entry separators in the Recent line.
_SPEC_ID_RE = re.compile(r"\b(\d{3}-[a-z0-9\-]+)\s+(?:Phase\s+\d+\s+)?(?:DONE|done|[A-Z]+)")

# Key paragraph labels we surface verbatim (one-liners).
_ONE_LINER_LABELS = ("**In Progress**", "**Next**", "**Roadmap**")


def build(ctx: ScanCtx) -> str:
    """Return a ≤5-bullet digest of progress-summary.md."""
    path = ctx.progress_path
    if not path.is_file():
        return _PLACEHOLDER

    text = path.read_text(encoding="utf-8")
    bullets = _extract_bullets(text)
    if not bullets:
        return _PLACEHOLDER

    return "\n".join(f"- {b}" for b in bullets[:5])


def _extract_bullets(text: str) -> list[str]:
    """Extract up to 5 digest bullets from progress-summary text."""
    bullets: list[str] = []

    # Pass 1: parse the **Recent**: line into individual spec entries.
    recent_bullets = _parse_recent_entries(text)
    bullets.extend(recent_bullets[:3])

    # Pass 2: extract one-liner paragraph labels.
    for label in _ONE_LINER_LABELS:
        line = _find_label_line(text, label)
        if line and len(bullets) < 5:
            bullets.append(line)

    return bullets


def _parse_recent_entries(text: str) -> list[str]:
    """Split the **Recent**: value on spec-id boundaries; return short labels."""
    # Find the **Recent**: paragraph (may span multiple lines).
    m = re.search(r"\*\*Recent\*\*:\s*(.+?)(?=\n\n|\n\*\*|\Z)", text, re.DOTALL)
    if not m:
        return []

    blob = m.group(1).replace("\n", " ").strip()

    # Split on ", NNN-" boundaries (entry separator pattern in progress-summary).
    # Each chunk is one spec entry.
    parts = re.split(r",\s*(?=\d{3}-)", blob)

    entries: list[str] = []
    for part in parts:
        part = part.strip().rstrip(",")
        if not part:
            continue
        # Shorten: keep only up to the first closing parenthesis or 120 chars.
        short = _shorten(part)
        if short:
            entries.append(short)

    return entries


def _shorten(text: str) -> str:
    """Return a short label from a spec-entry chunk."""
    # Extract spec-id + first noun phrase.
    m = re.match(r"(\d{3}-[a-z0-9\-]+)\s+(.*)", text)
    if not m:
        return text[:100]
    spec_id = m.group(1)
    body = m.group(2).strip()
    # Keep up to first sentence-ending period, comma, or 80 chars.
    end = min(
        (body.find(".") + 1 or len(body)),
        (body.find(" (") if " (" in body else len(body)),
        80,
    )
    summary = body[:end].rstrip(" ,.")
    return f"{spec_id} — {summary}" if summary else spec_id


def _find_label_line(text: str, label: str) -> str | None:
    """Return the content of the line starting with label, shortened."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(label):
            # Drop the label prefix, keep the value.
            value = stripped[len(label):].lstrip(":").strip()
            if value:
                return f"{label.strip('*')}: {value[:120]}"
    return None
