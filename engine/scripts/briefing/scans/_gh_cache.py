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
