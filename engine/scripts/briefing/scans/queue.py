"""scans/queue.py — section 4: My open queue (from gh-cache).

Port of briefing-build.sh lines 233-248.
Reads the gh-cache snapshot for the advisor, formats all rows as a list.
No live gh calls.

Enrichments (spec 084 Task 2.3):
  #8  issue-age  — appends "updated <N>d ago" when updated_at present in cache
  #14 repo-prefix — prefixes issue number with the repo short name (e.g. main-repo#N / ai-repo#N)
"""
from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from briefing.scans import ScanCtx

# Matches the json fence written by gh-fetch.sh (same regex as _gh_cache.py).
_JSON_FENCE_RE = re.compile(r"^```json\s*\n(.*?)\n```", re.DOTALL | re.MULTILINE)


def _age_label(updated_at: str) -> str:
    """Return a short human-readable age string from an ISO-8601 updated_at value.

    Returns empty string on any parse failure so callers can skip gracefully.
    """
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        days = (now - dt).days
        if days == 0:
            return "today"
        if days == 1:
            return "1d ago"
        return f"{days}d ago"
    except (ValueError, AttributeError):
        return ""


def _read_raw_items(cache_path: Path, advisor: str) -> list[dict]:
    """Parse gh-cache and return the raw JSON items list.

    Missing/corrupt cache → WARN to stderr + return [].
    """
    if not cache_path.is_file():
        print(
            f"WARN: gh-cache miss for {advisor} — run: "
            f"python -m engine lifecycle gh-fetch --advisor {advisor}",
            file=sys.stderr,
        )
        return []

    text = cache_path.read_text(encoding="utf-8")
    m = _JSON_FENCE_RE.search(text)
    if not m:
        return []
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return []


def _format_row(item: dict) -> str | None:
    """Format a single gh-cache item as an enriched queue line.

    Format: <repo>#<num> | <title> | <labels> | updated <age>
    The age and repo prefix are omitted gracefully when data is absent.
    """
    num = item.get("number")
    title = item.get("title", "")
    labels_raw = item.get("labels", [])
    labels = " ".join(lbl["name"] for lbl in labels_raw)

    if not title and num is None:
        return None

    # #14 repo prefix
    repo_name = (item.get("repository") or {}).get("name", "")
    prefix = repo_name
    if prefix:
        issue_ref = f"{prefix}#{num}"
    else:
        issue_ref = f"#{num}"

    # #8 issue age
    updated_at = item.get("updated_at", "")
    age = _age_label(updated_at) if updated_at else ""
    age_part = f" | updated {age}" if age else ""

    return f"{issue_ref} | {title} | {labels}{age_part}"


def build(ctx: ScanCtx) -> str:
    """Return markdown list of all open issues from gh-cache.

    Each line is enriched with repo prefix (#14) and issue age (#8).
    Placeholder: _(no open issues for advisor:<short_name>)_
    """
    cache_path = ctx.gh_cache_dir / f"{ctx.advisor}.md"
    items = _read_raw_items(cache_path, advisor=ctx.advisor)

    lines = []
    for item in items:
        row = _format_row(item)
        if row:
            lines.append(f"- {row}")

    if not lines:
        return f"_(no open issues for advisor:{ctx.short_name})_"
    return "\n".join(lines)
