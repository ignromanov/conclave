"""scans/mentions.py — section 7: Mentions (sorted priority then date desc).

Port of briefing-build.sh lines 291-333.
Reads open mentions from mentions_dir/<advisor>/open/*.md,
extracts `priority` and `created` frontmatter fields,
sorts by (rank asc, created desc) — p0 first, newest within same priority.

Enrichments (spec 084 Task 2.3):
  #5  priority + from + ref link + 1-line body excerpt appended to each line.
"""
from __future__ import annotations

import re
from datetime import datetime

from briefing.frontmatter_io import read as fm_read
from briefing.scans import ScanCtx

_PLACEHOLDER = "_(no open mentions)_"

_PRIO_RANK = {"p0": 0, "p1": 1, "p2": 2, "fyi": 3}
_DEFAULT_PRIO = "p2"
_DEFAULT_CREATED = "0000-00-00T00:00:00"

# Matches lines starting with "## Body" to find the body section.
_BODY_HEADING_RE = re.compile(r"^##\s+Body\s*$", re.MULTILINE)


def _format_created(raw_created: object) -> str:
    """Normalise a created value (datetime or string) to ISO-8601 string."""
    if isinstance(raw_created, datetime):
        if raw_created.tzinfo is not None:
            # strftime %z gives "+HHMM" — insert colon to match original.
            base = raw_created.strftime("%Y-%m-%dT%H:%M:%S")
            tz = raw_created.strftime("%z")
            # Insert colon: "-0300" → "-03:00"
            return f"{base}{tz[:-2]}:{tz[-2:]}"
        return raw_created.strftime("%Y-%m-%dT%H:%M:%S")
    return str(raw_created)


def _body_excerpt(body: str) -> str:
    """Return the first non-blank, non-heading line from the body (≤80 chars).

    Looks for a "## Body" section header; falls back to scanning from the top.
    Returns empty string when nothing useful is found.
    """
    # Try to skip to after a "## Body" heading.
    m = _BODY_HEADING_RE.search(body)
    text = body[m.end():] if m else body

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip markdown bold/italic markers for a clean one-liner.
        line = re.sub(r"\*{1,2}|_{1,2}", "", line)
        return line[:80] + ("…" if len(line) > 80 else "")
    return ""


def _build_ref(meta: dict) -> str:
    """Return a short reference string from ref_decision / ref_issue fields.

    Format examples:  "→ dec:solana-defer-beyond-v2"   "→ issue:AI#107"
    Returns empty string when neither field is set.
    """
    ref_decision = str(meta.get("ref_decision") or "").strip()
    ref_issue = str(meta.get("ref_issue") or "").strip()
    if ref_decision:
        return f"→ dec:{ref_decision}"
    if ref_issue:
        return f"→ issue:{ref_issue}"
    return ""


def build(ctx: ScanCtx) -> str:
    """Return markdown list of open mentions sorted priority asc, date desc.

    Format (enriched):
        - [<prio>] from:<from> [<id>](path) — <created> <ref> | <excerpt>

    Mirrors bash fm_get() + sort -t '|' -k1,1n -k2,2r exactly.
    """
    open_dir = ctx.mentions_dir / ctx.advisor / "open"
    if not open_dir.is_dir():
        return _PLACEHOLDER

    ment_files = sorted(open_dir.glob("*.md"))
    if not ment_files:
        return _PLACEHOLDER

    # Each entry: (rank, created_str, prio, mention_id, from_, ref, excerpt)
    entries: list[tuple[int, str, str, str, str, str, str]] = []
    for f in ment_files:
        mention_id = f.stem
        meta, body = fm_read(f)
        prio = str(meta.get("priority", _DEFAULT_PRIO) or _DEFAULT_PRIO)
        rank = _PRIO_RANK.get(prio, 4)
        raw_created = meta.get("created", _DEFAULT_CREATED) or _DEFAULT_CREATED
        created = _format_created(raw_created)
        from_ = str(meta.get("from") or "").strip()
        ref = _build_ref(meta)
        excerpt = _body_excerpt(body)
        entries.append((rank, created, prio, mention_id, from_, ref, excerpt))

    # Sort: rank ascending (p0 first), created descending (newer first).
    entries.sort(key=lambda e: (e[0], _negate_str(e[1])))

    lines: list[str] = []
    for _rank, created, prio, mention_id, from_, ref, excerpt in entries:
        path_ref = f"mentions/{ctx.advisor}/open/{mention_id}.md"
        # Build enriched line progressively.
        from_part = f" from:{from_}" if from_ else ""
        ref_part = f" {ref}" if ref else ""
        excerpt_part = f" | {excerpt}" if excerpt else ""
        lines.append(
            f"- [{prio}]{from_part} [{mention_id}]({path_ref})"
            f" — {created}{ref_part}{excerpt_part}"
        )

    return "\n".join(lines)


def _negate_str(s: str) -> str:
    """Invert a string for descending sort — mirrors sort -k2,2r.

    Replaces each character with its complement relative to max unicode
    codepoint for ascii printable range, so lexicographic ascending on
    the result is equivalent to descending on the original.

    For ISO-8601 date strings (0-9 / - T :) this is correct.
    """
    return "".join(chr(0x7E - ord(c)) if ord(c) <= 0x7E else c for c in s)
