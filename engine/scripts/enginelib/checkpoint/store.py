"""store.py — where the in-flight record lives and how a line reaches it (spec 117 T4).

`record.py` decides what a line looks like; this decides which file it goes into and how it
gets there. The split is the 099 one: nothing here prints, parses argv or exits.

**The path is derived, never chosen.** `{date}-{advisor}-{token}.md` under
`paths.checkpoints_dir()`, with the session token in the slug's position — the grammar
`rename.py` already parses positionally (`_DATE_PREFIX:87`, `_id_positions:658`), so the new
directory works the day that code is pointed at it instead of needing a second parser.

**R7 needs no check, and that is the design.** Two sessions of one advisor receive different
`CLAUDE_CODE_SESSION_ID` values, therefore different tokens, therefore different filenames. The
operating system enforces the fencing; a verb that derives its path from the ambient token
cannot append to another session's record even deliberately. A structural guarantee is worth
more than a refusal that has to be tested — and tests of a refusal are what rot.

**An absent token degrades rather than inventing one.** `hot.py` makes no fencing claim without
a token and neither does this: the record is named `unfenced`, both sessions share it, and the
caller is told. Minting an identifier to fill the gap would manufacture a distinction that is
not there — and give one session two identities, since hot.md's `Now` line would still be
fenced by nothing.

**Creation is `O_EXCL`, appending is `O_APPEND`, and neither is `fsync`ed.** The exclusive
create is not ceremony: `session_init` runs twice per Claude session under one token, so two
processes can reach a missing record at the same moment, and a plain "write the header if
absent" loses whichever lines the loser already appended. The missing `fsync` is the trade
`record.py` documents — A1 is process death, and the page cache outlives a killed process.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from enginelib import paths
from enginelib.checkpoint import record
from enginelib.memory.hot import session_token

#: What the file is called when the harness gave us no session id to fence on.
UNFENCED = "unfenced"

#: `briefing/schema.py:62`'s `Checkpoint` model — type, owner, created, session, schema_version.
#: Registered there before this producer existed, deliberately, so the first record written
#: validates instead of becoming an ERROR wherever it sits.
SCHEMA_VERSION = 1


def token_for(session_id: str | None) -> str:
    """The slug position of the filename: the fencing token, or `unfenced`."""
    return session_token(session_id) or UNFENCED


def record_path(advisor: str, session_id: str | None, *, today: str | None = None,
                directory: Path | None = None) -> Path:
    stamp = today or datetime.now().astimezone().strftime("%Y-%m-%d")
    base = directory if directory is not None else paths.checkpoints_dir()
    return base / f"{stamp}-{advisor}-{token_for(session_id)}.md"


def _header(advisor: str, token: str) -> str:
    return (
        "---\n"
        "type: checkpoint\n"
        f"owner: {advisor}\n"
        f"created: {datetime.now().astimezone().isoformat(timespec='seconds')}\n"
        f"session: {token}\n"
        f"schema_version: {SCHEMA_VERSION}\n"
        "---\n"
        "\n"
    )


def ensure(advisor: str, session_id: str | None, *, today: str | None = None,
           directory: Path | None = None) -> Path:
    """The record's path, with its frontmatter written if this is the first caller.

    `O_EXCL` rather than `if not path.exists()`: the loser of that race truncates the winner's
    appended lines, and the race is reachable — session_init runs twice per session under one
    token. Losing the create is the normal outcome, not an error.
    """
    path = record_path(advisor, session_id, today=today, directory=directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return path
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(_header(advisor, token_for(session_id)))
    return path


def append(path: Path, line: str) -> None:
    """One rendered line plus its newline, through `O_APPEND` (what mode "a" opens)."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read(path: Path) -> record.Reading:
    """The record's entries and its damaged lines. Missing file reads as empty, not as an error.

    Decoded with `errors="replace"` because a torn write can land mid-character: the body is
    UTF-8 prose, so the tear has nothing to do with the sentinel's own encoding. A reader that
    raised `UnicodeDecodeError` here would turn the interruption 117 exists to make visible
    into a crash that hides it.
    """
    if not path.is_file():
        return record.Reading((), ())
    return record.read(path.read_bytes().decode("utf-8", errors="replace"))
