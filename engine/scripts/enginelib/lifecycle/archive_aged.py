"""enginelib.lifecycle.archive_aged — I/O-free core for the archive-aged sweep.

Contract: no stdout, no argparse, no sys.exit. File reads and writes are
allowed (mutates files via snapshot_write). Port of lifecycle/archive-aged.sh.

run() returns list[Path] — the matched candidates (dry_run=True) or the mutated
paths (dry_run=False). Deviation from the plan's loose `-> int`: returning the
list lets the adapter print per-file WOULD ARCHIVE: lines and derive the count
as len(...).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from enginelib.snapshot import snapshot_write

# Match the tags: line for status/resolved or status/archived.
# re.MULTILINE so ^ anchors to line start, mirroring bash grep -E '^tags:...'
_RESOLVED = re.compile(r"^tags:.*status/resolved", re.MULTILINE)
_ARCHIVED = re.compile(r"^tags:.*status/archived", re.MULTILINE)

# Substitution pattern: first occurrence of status/resolved on a tags: line.
# Mirrors: sed -E 's/(^tags:.*)(status\/resolved)/\1status\/archived/'
_SUB = re.compile(r"^(tags:.*?)status/resolved", re.MULTILINE)


def run(root: Path, age_days: int = 30, dry_run: bool = False) -> list[Path]:
    """Sweep *.md files under root older than age_days days.

    Keeps only files with a tags: line matching status/resolved that do NOT
    already have status/archived (idempotent). Mutates the tags: line in-place
    (status/resolved → status/archived) via atomic snapshot_write; other tags
    and the file body are untouched.

    Returns the list of candidate paths (dry_run) or mutated paths (live run).
    """
    threshold = age_days * 86400
    now = time.time()

    candidates: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        if (now - path.stat().st_mtime) <= threshold:
            continue
        content = path.read_text(encoding="utf-8")
        if not _RESOLVED.search(content):
            continue
        if _ARCHIVED.search(content):
            continue
        candidates.append((path, content))

    if dry_run:
        return [p for p, _ in candidates]

    result: list[Path] = []
    for path, content in candidates:
        new_content = _SUB.sub(r"\1status/archived", content, count=1)
        snapshot_write(path, new_content)
        result.append(path)
    return result
