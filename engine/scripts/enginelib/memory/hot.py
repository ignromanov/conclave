"""enginelib.memory.hot — initialize, append to and remove from agent-memory/hot.md.

Port of hot-md-init.sh and hot-md-append.sh. I/O-free of stdout/argparse/sys.exit
(file I/O, subprocess for regen, clock OK).

Most sections only ever grow. `now` is not: it holds the sessions that are
open *right now*, so it needs a subtraction too — session_init appends on open,
close_session removes the same line on close (#149). remove() is that counterpart.
"""
from __future__ import annotations

import logging
import os
import re
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

# A seeded, contentless bullet: "- (none)", "- (waiting for first append)". Real
# entries always start "- [<timestamp>] ", so the shapes cannot collide.
_PLACEHOLDER_RE = re.compile(r"^- \([^\[\]]*\)\s*$")
_EMPTY_PLACEHOLDER = "- (none)"

# The Now entry's content, shared by the two ends of the session lifecycle:
# session_init appends it, close_session removes by it. It lives here rather than
# as a literal in each caller because a match key spelled twice is a match key that
# will eventually be spelled two ways — the defect class that left Now empty (#149).
SESSION_OPEN = "session open"

# What an entry becomes when the next session finds it still open. It deliberately
# shares no substring with SESSION_OPEN: close_session drains Now by that key, and a
# superseded line that still matched would be destroyed by the very next close --
# which is how the evidence was lost the first time (#229).
SESSION_NEVER_CLOSED = "session never closed"

_TEMPLATE = """\
# Hot — live memory

> ≤500 words. Only scripts write here; every section only grows except Now, which drains as sessions close. Compaction on overflow. Read at /team.start, written at /team.done + on file-decision/mention.

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


def session_open_line(token: str) -> str:
    """The `Now` entry content for an open session, fenced by its session token.

    The token is what distinguishes "this session, registering again" from "a session
    that never closed": session-init runs twice per Claude session -- once from the
    SessionStart hook for every advisor, once from the bound advisor's skill -- so a
    bare re-registration must be a no-op, not a report of an abandoned session
    (spec 117 R7). Truncated to 8 characters on the git short-sha convention: the line
    is read by humans in hot.md, and 8 hex characters do not collide within an
    instance's history.

    An empty token yields the bare key, which is the pre-token behaviour: with nothing
    to fence on, two sessions are indistinguishable and none may be called stale.
    """
    token = (token or "").strip()[:8]
    return f"{SESSION_OPEN} ({token})" if token else SESSION_OPEN


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
            elif in_section and _PLACEHOLDER_RE.match(raw_line):
                # The seed bullet yields to the first real entry — otherwise a
                # populated section still renders "- (none)" above its content (#149)
                continue
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


def remove(section: str, advisor: str, match: str) -> int:
    """Remove the entries an advisor put in a section, by content match.

    The subtraction half of the Now lifecycle (#149): session_init appends when a
    session opens, close_session removes the same line when it closes, so the
    section shows what is genuinely in flight rather than a log of everything that
    ever started.

    Matching is deliberately narrow — an entry must carry BOTH this advisor's
    authorship marker and the `match` substring. Two advisors working the same slug
    have two lines in Now, and closing one must not drain the other's.

    Args:
        section: one of: now, open-threads, recent-decisions, watch
        advisor: advisor or executor identifier — the entry's author
        match:   substring the entry's content must contain

    Returns:
        The number of entries removed (0 when nothing matched — not an error; a
        session may legitimately close without ever having been registered).

    Raises:
        ValueError:        empty args, invalid section, or section header missing
        FileNotFoundError: hot.md does not exist
    """
    if not section:
        raise ValueError("section is required")
    if not advisor:
        raise ValueError("advisor is required")
    if not match:
        raise ValueError("match is required")

    if section not in _SECTION_MAP:
        raise ValueError(f"invalid section: {section}")
    header = _SECTION_MAP[section]

    hot = paths.hot_md_path()
    if not hot.is_file():
        raise FileNotFoundError(f"hot.md not found at {hot} — run engine memory hot-init")

    author_marker = f"] {advisor}: "
    lock_file = Path(os.environ.get("LOCK_DIR", "/tmp/conclave-locks")) / "hot-md.lock"

    with with_lock(lock_file):
        raw_lines = hot.read_text(encoding="utf-8").rstrip("\n").split("\n")

        out: list[str] = []
        in_section = False
        header_found = False
        removed = 0
        kept_bullets = 0

        def close_section() -> None:
            # Exactly one placeholder, and only when the section ends up empty. Seeded
            # placeholders are dropped on the way through rather than kept, because a
            # legacy section can hold both a placeholder and real entries (live Watch
            # does) — emitting them and then adding one here would leave two.
            if kept_bullets == 0:
                out.append(_EMPTY_PLACEHOLDER)

        for raw_line in raw_lines:
            if raw_line == header:
                out.append(raw_line)
                in_section = True
                header_found = True
                continue
            if in_section and raw_line.startswith("## "):
                close_section()
                in_section = False
                out.append(raw_line)
                continue
            if in_section and raw_line.startswith("- "):
                if author_marker in raw_line and match in raw_line:
                    removed += 1
                    continue
                if _PLACEHOLDER_RE.match(raw_line):
                    continue  # re-emitted by close_section() only if still needed
                kept_bullets += 1
            out.append(raw_line)

        if in_section:
            close_section()

        if not header_found:
            raise ValueError(f"section header not found: {header}")

        if not removed:
            return 0

        snapshot_write(hot, "\n".join(out) + "\n")

    return removed


def supersede_stale_session(advisor: str, token: str) -> list[str]:
    """Move this advisor's `Now` entries from *other* sessions into `Open threads`.

    Spec 117 R9: a start may not erase an unclosed session record, only mark it
    superseded. Before this, session_init opened with an unconditional
    `remove("now", advisor, SESSION_OPEN)`, so every start deleted whatever the last
    one left behind -- 4 of the 9 `session open` entries this instance ever committed
    vanished with no close and no trace (44%).

    `Open threads` is the destination because it is grow-only and already means
    "unfinished". The moved line keeps the original timestamp, so the age of the
    abandonment survives, and drops the SESSION_OPEN key, so the next close cannot
    drain it (see SESSION_NEVER_CLOSED).

    Args:
        advisor: the entry's author -- another advisor's open session is never touched
        token:   the *current* session's fencing token; entries carrying it are this
                 session's own and stay put

    Returns:
        The stale entries, verbatim, in file order -- the caller surfaces them.
        Empty when there is nothing to supersede, or when `token` is empty (with no
        token the two cases are indistinguishable, and a report that cannot be told
        apart from a false one is worse than no report).

    Raises:
        ValueError:        empty advisor, or a section header missing
        FileNotFoundError: hot.md does not exist
    """
    if not advisor:
        raise ValueError("advisor is required")
    token = (token or "").strip()[:8]
    if not token:
        return []

    hot = paths.hot_md_path()
    if not hot.is_file():
        raise FileNotFoundError(f"hot.md not found at {hot} -- run engine memory hot-init")

    author_marker = f"] {advisor}: "
    own_fence = f"({token})"
    now_header = _SECTION_MAP["now"]
    threads_header = _SECTION_MAP["open-threads"]
    stamp = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z")
    lock_file = Path(os.environ.get("LOCK_DIR", "/tmp/conclave-locks")) / "hot-md.lock"

    with with_lock(lock_file):
        raw_lines = hot.read_text(encoding="utf-8").rstrip("\n").split("\n")

        stale: list[str] = []
        in_now = False
        for raw_line in raw_lines:
            if raw_line == now_header:
                in_now = True
                continue
            if in_now and raw_line.startswith("## "):
                in_now = False
                continue
            if (
                in_now
                and raw_line.startswith("- ")
                and author_marker in raw_line
                and SESSION_OPEN in raw_line
                and own_fence not in raw_line
            ):
                stale.append(raw_line)

        if not stale:
            return []

        moved: list[str] = []
        for raw_line in stale:
            # author_marker is present by construction, so partition always splits.
            head, _, content = raw_line.partition(author_marker)
            note = content.replace(SESSION_OPEN, SESSION_NEVER_CLOSED, 1)
            moved.append(f"{head}{author_marker}{note} -- superseded at {stamp}")

        out: list[str] = []
        in_now = False
        in_threads = False
        now_kept = 0
        now_found = False
        threads_found = False

        for raw_line in raw_lines:
            # Close the open section before opening the next one -- the two sections
            # are adjacent in the template, so testing for the new header first would
            # leave Now unterminated and spill its placeholder into Open threads.
            if raw_line.startswith("## "):
                if in_now and now_kept == 0:
                    out.append(_EMPTY_PLACEHOLDER)
                if in_threads:
                    out.extend(moved)
                in_now = in_threads = False
                out.append(raw_line)
                if raw_line == now_header:
                    in_now, now_found = True, True
                elif raw_line == threads_header:
                    in_threads, threads_found = True, True
                continue
            if in_now and raw_line.startswith("- "):
                if raw_line in stale or _PLACEHOLDER_RE.match(raw_line):
                    continue
                now_kept += 1
            if in_threads and _PLACEHOLDER_RE.match(raw_line):
                continue
            out.append(raw_line)

        if in_now and now_kept == 0:
            out.append(_EMPTY_PLACEHOLDER)
        if in_threads:
            out.extend(moved)

        for found, header in ((now_found, now_header), (threads_found, threads_header)):
            if not found:
                raise ValueError(f"section header not found: {header}")

        snapshot_write(hot, "\n".join(out) + "\n")

    return stale
