"""scans/_gh_cache.py — shared gh-cache reader.

Port of briefing-build.sh read_gh_cache() (lines 110-163).
Reads the snapshot written by gh-fetch.sh. No live gh calls.
Returns a list of "#<num> | <title> | <labels>" strings.
Logs WARN to stderr on cache miss; INFO on stale — always returns data.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# TTL in seconds matching briefing-build.sh.
_CACHE_TTL = 900

# Regex to extract the ```json ... ``` fence from the cache file.
_JSON_FENCE_RE = re.compile(r"^```json\s*\n(.*?)\n```", re.DOTALL | re.MULTILINE)


def read_gh_cache(cache_path: Path, *, advisor: str) -> list[str]:
    """Parse gh-cache snapshot and return issue rows.

    Each row: "#<number> | <title> | <label1> <label2> ..."

    Mirrors bash read_gh_cache() exactly:
    - Missing file → WARN to stderr, return [].
    - Stale file   → INFO to stderr, still return data.
    - No json fence → return [].
    """
    if not cache_path.is_file():
        print(
            f"WARN: gh-cache miss for {advisor} — run: "
            f"python -m engine lifecycle gh-fetch --advisor {advisor}",
            file=sys.stderr,
        )
        return []

    # Stale check.
    mtime = cache_path.stat().st_mtime
    age = int(time.time() - mtime)
    if age > _CACHE_TTL:
        print(
            f"INFO: gh-cache stale for {advisor} by {age}s — "
            f"rerun: python -m engine lifecycle gh-fetch --advisor {advisor}",
            file=sys.stderr,
        )

    text = cache_path.read_text(encoding="utf-8")
    m = _JSON_FENCE_RE.search(text)
    if not m:
        return []

    json_block = m.group(1)
    try:
        items = json.loads(json_block)
    except json.JSONDecodeError:
        return []

    rows: list[str] = []
    for item in items:
        num = item.get("number", "")
        title = item.get("title", "")
        labels = " ".join(lbl["name"] for lbl in item.get("labels", []))
        rows.append(f"#{num} | {title} | {labels}")
    return rows


# Frontmatter stamp written by gh-fetch.sh: captured_at: "2026-09-09T21:51:08Z".
_CAPTURED_AT_RE = re.compile(r'^captured_at:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)


def captured_at(cache_path: Path) -> datetime | None:
    """When this snapshot was taken, from its own frontmatter — not its mtime.

    An instance-wide count is a union of these snapshots, and its honesty depends
    on the OLDEST of them (see `enginelib.status.reduce.Mosaic`). mtime would be
    the convenient source and the wrong one: any tool that rewrites or copies the
    file moves the mtime without re-fetching anything, so mtime answers "when did
    this file last change" while the projection is asking "how old is this view of
    GitHub". `read_gh_cache`'s own staleness INFO uses mtime for TTL, which is a
    different question with a different tolerance; this is deliberately not that.

    None when the file is absent or carries no parsable stamp — the caller must
    then treat the shard as missing rather than as fresh.
    """
    if not cache_path.is_file():
        return None
    m = _CAPTURED_AT_RE.search(cache_path.read_text(encoding="utf-8"))
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
