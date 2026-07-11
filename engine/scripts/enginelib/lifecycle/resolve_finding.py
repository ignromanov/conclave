"""enginelib.lifecycle.resolve_finding — I/O-free core for audit-finding resolution.

Contract: no stdout, no argparse, no sys.exit. File reads and writes are allowed
(mutates the finding via snapshot_write). Port of lifecycle/resolve-finding.sh.

run() returns a status string:
  "no-tags"  — file lacks both status/open and status/resolved; no write.
  "noop"     — already status/resolved with the same note; byte-identical; no write.
  "resolved" — file updated: tags line patched, Resolution block appended/replaced.
"""
from __future__ import annotations

import re
from pathlib import Path

from enginelib.snapshot import snapshot_write

_HAS_OPEN = re.compile(r"^tags:.*status/open", re.MULTILINE)
_HAS_RESOLVED = re.compile(r"^tags:.*status/resolved", re.MULTILINE)
_OPEN_TO_RESOLVED = re.compile(r"^(tags:.*?)status/open", re.MULTILINE)


def run(path: Path, note: str) -> str:
    """Transition a status/open audit-finding to status/resolved.

    Idempotency: status/resolved + same note text → "noop" (no write).
    Re-resolve:  status/resolved + different note → Resolution block replaced.
    """
    text = path.read_text(encoding="utf-8")

    has_open = bool(_HAS_OPEN.search(text))
    has_resolved = bool(_HAS_RESOLVED.search(text))

    if not has_open and not has_resolved:
        return "no-tags"

    # Idempotent no-op: already resolved with the exact same note text anywhere in file.
    if has_resolved and note in text:
        return "noop"

    # Strip any prior ## Resolution section (port of the awk block).
    kept = []
    in_resolution = False
    for line in text.splitlines():
        if line == "## Resolution":
            in_resolution = True
            continue
        if in_resolution:
            if line.startswith("## "):
                in_resolution = False
                # fall through to keep this heading
            else:
                continue
        kept.append(line)
    stripped = "\n".join(kept)

    # Replace status/open → status/resolved on the tags: line (preserves other tags).
    stripped = _OPEN_TO_RESOLVED.sub(r"\1status/resolved", stripped, count=1)

    # Append Resolution block.
    new_body = f"{stripped}\n## Resolution\n{note}\n"

    snapshot_write(path, new_body)
    return "resolved"
