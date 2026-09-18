"""record.py — one checkpoint line: how it is written, and how a torn one is told apart.

Spec 117 R2 (a unit may be *declared* before it is *completed*; the two are distinct lines)
and R5 (`requested N · shipped M · lost K`). The format decision is the plan's D2.

**Why a per-line sentinel and not just a newline.** The record is appended with `O_APPEND`,
and a torn write leaves a prefix, never a suffix — so "the last line has no newline" would in
fact catch a truncated tail. It is the *middle* of the file that needs the sentinel:
`session_init` runs twice per Claude session (once from the SessionStart hook, once from the
bound advisor's skill) under one token, therefore against one file, so two processes can be
appending at once. Interleave two writes and the file holds a fragment, a whole line, and the
other fragment — the whole line reads clean and sits in the middle, where a newline rule never
looks. The sentinel makes completeness a property of **each line**, not of its position.

**A torn tail is discarded and reported, never an error.** A1 kills the process on purpose, so
recovery is on the acceptance path: a reader that raised would turn the interruption 117 exists
to make visible into a crash that hides it. `read()` returns the intact entries *and* the lines
it dropped; refusing to decide between them is what a diary does.

**No `fsync` per append** — not laziness, a stated trade. A1 is SIGKILL and terminal-close, i.e.
process death, and the page cache outlives a killed process. Research W4 §3 (Rebello et al.,
USENIX ATC 2020) is the other half: a failed `fsync` can mark the dirty page clean regardless,
so the *next* `fsync` reports success over data that is already gone. Paying per-append latency
for a barrier that does not hold against the failure it is bought for is the worse trade.

The timestamp grammar is `hot.py`'s, to the minute, on purpose: hot.md's `Now` line and this
record are joined by the same session token, and a shared stamp format means the join needs no
second parser. Minute resolution is what A2 measures against (are the lines clustered in the
final five minutes?), so it is the resolution the acceptance criterion needs.

No filesystem, no subprocess, no stdout: rendering, parsing and the tally are all pure. The
adapter owns the open/append/read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

#: Terminal marker of a complete line. Multi-byte on purpose is *not* the claim — a tear can
#: land mid-character anywhere in a UTF-8 body regardless, so the caller must decode
#: defensively (`errors="replace"`) whatever this is. It is one character, rare in prose, and
#: reads as machine-owned to anyone opening the file.
SENTINEL = "¶"

KIND_INTENT = "intent"
KIND_DONE = "done"
KINDS = (KIND_INTENT, KIND_DONE)

#: `2026-09-15T16:01-0300` — `enginelib.memory.hot`'s stamp, character for character.
TS_FORMAT = "%Y-%m-%dT%H:%M%z"

#: The evidence suffix's opening. Rejected inside free text (see `render`) because the parser
#: would otherwise read a unit that merely *mentions* it as one that carries evidence.
_EV_OPEN = "[ev: "

_LINE_PREFIX = "- ["

_ENTRY_RE = re.compile(
    r"^- \[(?P<ts>[^\]]+)\] (?P<kind>intent|done): (?P<text>.+?)"
    r"(?: \[ev: (?P<ev>[^\]]*)\])? " + re.escape(SENTINEL) + r"$"
)


@dataclass(frozen=True)
class Entry:
    """One complete line. `evidence` holds the refs as written — resolving them is T3's job."""

    kind: str
    ts: str
    text: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class Reading:
    """What a file yielded: the lines that survived, and the ones that did not."""

    entries: tuple[Entry, ...]
    discarded: tuple[str, ...]


@dataclass(frozen=True)
class Tally:
    """R5's row, in R5's vocabulary.

    `requested` counts every distinct unit the record names, declared or not: a unit completed
    without a prior intent line is still work that was asked for, and R2 makes the intent line
    optional ("*may* be declared"). Counting only declared units would let `shipped` exceed
    `requested` and make the row read as nonsense on the one path R2 explicitly allows.

    The invariant that falls out, and that the tests pin: `requested == shipped + len(lost)`.
    """

    requested: int
    shipped: int
    lost: tuple[str, ...]


def now_stamp() -> str:
    return datetime.now().astimezone().strftime(TS_FORMAT)


def render(
    kind: str,
    text: str,
    *,
    evidence: tuple[str, ...] | list[str] = (),
    ts: str | None = None,
) -> str:
    """One line, sentinel included, newline excluded — the adapter adds that with the append.

    Raises ValueError rather than sanitising. Text is free-form and arrives from an agent, so
    it is the format's only injection surface: a newline in it forges a line boundary and a
    sentinel in it forges a completion. Both would be *silently* well-formed, which is the one
    thing a record read for evidence cannot afford. A refused line is visible; a forged one is
    not.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown checkpoint kind {kind!r} — expected one of {KINDS}")
    text = text.strip()
    if not text:
        raise ValueError("a checkpoint line must name the unit; empty text was given")
    for bad, why in (("\n", "newline"), ("\r", "carriage return"), (SENTINEL, "sentinel"),
                     (_EV_OPEN, "evidence marker")):
        if bad in text:
            raise ValueError(f"checkpoint text may not contain a {why}: {text!r}")
    refs = tuple(r.strip() for r in evidence if r.strip())
    for ref in refs:
        for bad in ("\n", "\r", ",", "]", SENTINEL):
            if bad in ref:
                raise ValueError(f"evidence ref may not contain {bad!r}: {ref!r}")
    suffix = f" {_EV_OPEN}{', '.join(refs)}]" if refs else ""
    return f"- [{ts or now_stamp()}] {kind}: {text}{suffix} {SENTINEL}"


def parse(line: str) -> Entry | None:
    """An Entry, or None when the line is not a complete rendered line."""
    m = _ENTRY_RE.match(line)
    if m is None:
        return None
    ev = m.group("ev")
    refs = tuple(r.strip() for r in ev.split(",") if r.strip()) if ev else ()
    return Entry(kind=m.group("kind"), ts=m.group("ts"), text=m.group("text"), evidence=refs)


def _is_candidate(line: str) -> bool:
    """Was this line *trying* to be an entry?

    Three shapes qualify: a rendered line, a prefix of one (what a torn write leaves), and
    anything carrying the sentinel (what the far side of an interleave leaves). Everything
    else — the frontmatter fence, its keys, a blank — is prose the record is allowed to hold,
    and reporting it as discarded would bury the one line that actually was.
    """
    return (
        line.startswith(_LINE_PREFIX)
        or _LINE_PREFIX.startswith(line)
        or line.endswith(SENTINEL)
    )


def read(text: str) -> Reading:
    """Classify every line of a record's text. Frontmatter and blanks are ignored, not dropped."""
    entries: list[Entry] = []
    discarded: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        entry = parse(line)
        if entry is not None:
            entries.append(entry)
        elif _is_candidate(line):
            discarded.append(line)
    return Reading(tuple(entries), tuple(discarded))


def tally(entries: tuple[Entry, ...] | list[Entry]) -> Tally:
    """`requested N · shipped M · lost K`, computed from the parsed lines and nothing else.

    Units are keyed by their text, deduplicated in first-seen order: re-declaring an intent is
    a human repeating themselves, not a second unit of work.
    """
    units = {e.text: None for e in entries}
    shipped = {e.text: None for e in entries if e.kind == KIND_DONE}
    lost = tuple(t for t in units if t not in shipped)
    return Tally(requested=len(units), shipped=len(shipped), lost=lost)
