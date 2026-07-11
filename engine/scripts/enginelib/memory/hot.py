"""enginelib.memory.hot — initialize and append to agent-memory/hot.md.

Port of hot-md-init.sh and hot-md-append.sh. I/O-free of stdout/argparse/sys.exit
(file I/O, subprocess for regen, clock OK).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from enginelib import advisors, paths
from enginelib.lock import with_lock
from enginelib.snapshot import snapshot_write

_log = logging.getLogger(__name__)

_SECTION_MAP = {
    "now": "## Now",
    "open-threads": "## Open threads",
    "recent-decisions": "## Recent decisions",
    "watch": "## Watch",
}

_TEMPLATE = """\
# Hot — live memory

> ≤500 words. Append-only via scripts; compaction on overflow. Read at /team.start, written at /team.done + on file-decision/mention.

## Now

- (waiting for first append)

## Open threads

- (none)

## Recent decisions

- (none)

## Watch

- (none)

## Last updated

{today} by engine memory hot-init
"""


def init(force: bool = False, hot_path: Path | None = None) -> str:
    """Initialize hot.md from template.

    Returns "exists" if file already exists and force is False (no write).
    Returns "wrote" after writing the template.
    Raises OSError/PermissionError if the parent dir is unwritable.

    `hot_path` overrides the default `paths.hot_md_path()` target — callers with
    their own root resolution (e.g. session_init, whose repo_root diverges on the
    CLAUDE_PROJECT_DIR branch) pass it to seed exactly the file they read (#49b).
    """
    hot = hot_path if hot_path is not None else paths.hot_md_path()
    if hot.is_file() and not force:
        return "exists"
    paths.ensure_dir(hot.parent)
    today = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z")
    body = _TEMPLATE.format(today=today)
    snapshot_write(hot, body)
    return "wrote"


def _compact_text(body: str) -> str:
    """Compact Recent decisions to last 5 bullets; preserve everything else.

    Replicates the bash compaction awk in hot-md-append.sh.
    Blanks and non-bullet lines inside the section are dropped.
    """
    out: list[str] = []
    in_rd = False
    rd: list[str] = []

    for raw_line in body.rstrip("\n").split("\n"):
        if raw_line == "## Recent decisions":
            in_rd = True
            out.append(raw_line)
            continue
        if raw_line.startswith("## ") and in_rd:
            kept = rd[-5:] if len(rd) > 5 else rd
            out.extend(kept)
            if kept:
                out.append("")
            rd = []
            in_rd = False
            out.append(raw_line)
            continue
        if in_rd:
            if raw_line.startswith("- "):
                rd.append(raw_line)
            # else: eat blank lines and non-bullet content inside the section
            continue
        out.append(raw_line)

    # EOF inside Recent decisions — flush without trailing blank
    if in_rd and rd:
        kept = rd[-5:] if len(rd) > 5 else rd
        out.extend(kept)

    return "\n".join(out) + "\n"


def append(section: str, advisor: str, line: str, no_compact: bool = False) -> str:
    """Atomically append a timestamped entry to a hot.md section.

    Port of hot-md-append.sh. I/O-free of stdout/argparse/sys.exit.

    Args:
        section:    one of: now, open-threads, recent-decisions, watch
        advisor:    advisor or executor identifier
        line:       single-line content (no newlines)
        no_compact: skip post-append compaction

    Returns:
        The formatted entry string.

    Raises:
        ValueError:        empty args, invalid section, or section header missing
        FileNotFoundError: hot.md does not exist
    """
    if not section:
        raise ValueError("section is required")
    if not advisor:
        raise ValueError("advisor is required")
    if not line:
        raise ValueError("line is required")

    if section not in _SECTION_MAP:
        raise ValueError(f"invalid section: {section}")
    header = _SECTION_MAP[section]

    hot = paths.hot_md_path()
    if not hot.is_file():
        raise FileNotFoundError(f"hot.md not found at {hot} — run engine memory hot-init")

    today = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z")
    entry = f"- [{today}] {advisor}: {line}"

    lock_file = Path(os.environ.get("LOCK_DIR", "/tmp/conclave-locks")) / "hot-md.lock"

    with with_lock(lock_file):
        raw_lines = hot.read_text(encoding="utf-8").rstrip("\n").split("\n")

        out: list[str] = []
        in_section = False
        in_last = False
        updated = False
        header_found = False

        for raw_line in raw_lines:
            if raw_line == header:
                out.append(raw_line)
                in_section = True
                header_found = True
                continue
            if in_section and raw_line.startswith("## "):
                # Insert entry just before next header (bash awk ordering)
                out.append(entry)
                out.append("")
                in_section = False
            if raw_line == "## Last updated":
                in_last = True
                out.append(raw_line)
                continue
            if in_last and not updated and raw_line.strip() and not raw_line.startswith(">"):
                out.append(f"{today} by {advisor}")
                in_last = False
                updated = True
                continue
            out.append(raw_line)

        # Section was the last block in the file
        if in_section:
            out.append(entry)

        if not header_found:
            raise ValueError(f"section header not found: {header}")

        snapshot_write(hot, "\n".join(out) + "\n")

        # Compaction serialized under the same lock — no mtime-race guard needed
        if not no_compact:
            current = hot.read_text(encoding="utf-8")
            if len(current.split()) > 500:
                snapshot_write(hot, _compact_text(current))

    # Layer-1 briefing regen (best-effort, fd-suppressed; mirrors mention.create)
    if advisors.is_canonical_advisor(advisor):
        try:
            import sys as _sys

            from briefing.regen import regen_advisor
            _sys.stdout.flush()
            _devnull = os.open(os.devnull, os.O_WRONLY)
            _saved = os.dup(1)
            os.dup2(_devnull, 1)
            os.close(_devnull)
            try:
                regen_advisor(advisor)
            finally:
                _sys.stdout.flush()
                os.dup2(_saved, 1)
                os.close(_saved)
        except (ImportError, OSError):
            _log.debug("briefing regen for advisor skipped (expected)", exc_info=True)
        except Exception:
            _log.warning("briefing regen for advisor failed unexpectedly", exc_info=True)

    return entry
