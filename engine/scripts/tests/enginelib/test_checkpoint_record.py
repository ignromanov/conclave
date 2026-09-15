"""test_checkpoint_record.py — the checkpoint line format (spec 117 T2, plan D2).

Every test here is named by the mutation it must redden under. A round-trip test would pass
with the sentinel check deleted, the injection guards deleted and the tally counting the wrong
set — which is to say it would measure nothing. What the format is *for* is a record that
survives the process being killed mid-write, so the fixtures are damaged on purpose.

Pure: no tmp_path, no filesystem. The module under test touches neither.
"""
from __future__ import annotations

import pytest

from enginelib.checkpoint.record import (
    SENTINEL,
    Entry,
    parse,
    read,
    render,
    tally,
)

_TS = "2026-09-15T16:01-0300"


def _record(*lines: str) -> str:
    """A record's text: real frontmatter, then the given body lines."""
    return "---\ntype: checkpoint\nowner: sage-cto\n---\n\n" + "\n".join(lines) + "\n"


def test_a_torn_tail_is_discarded_and_named_rather_than_parsed():
    """Mutation: drop the sentinel from `_ENTRY_RE`.

    The tail below is a byte-exact prefix of a rendered line — what `O_APPEND` leaves when the
    process dies mid-write. Without the sentinel requirement it matches the grammar and enters
    the record as a completed unit called "T9 — the branch", which is a unit nobody ever named.
    That is the whole reason the sentinel is per line and not implied by the newline.

    The frontmatter assertion rides along for a different mutation: widen `_is_candidate` and
    `type: checkpoint` is reported as a damaged line, burying the one that is.
    """
    whole = render("intent", "T1 — checkpoints_dir", ts=_TS)
    torn = render("done", "T9 — the branch × PR-state join", ts=_TS)
    torn = torn[: torn.index("branch") + len("branch")]

    reading = read(_record(whole, torn))

    assert reading.entries == (Entry(kind="intent", ts=_TS, text="T1 — checkpoints_dir"),)
    assert reading.discarded == (torn,)
    assert all("branch" not in e.text for e in reading.entries)


def test_a_fragment_in_the_middle_survives_where_a_newline_rule_would_not():
    """Mutation: replace the per-line sentinel check with "the last line ends in a newline".

    `session_init` runs twice per Claude session under one token, so two processes append to
    one file. Interleaved, a torn write's two halves end up on either side of somebody else's
    complete line — and the fragments are then *not* at the end of the file, where a newline
    rule is the only thing that ever looks. Both fragments must be discarded and the complete
    line between them must survive.
    """
    complete = render("intent", "T2 — the record format", ts=_TS)
    head, tail = "- [2026-09-15T16:02-0300] done: T3 — evide", "nce resolvers " + SENTINEL

    reading = read(_record(head, complete, tail))

    assert [e.text for e in reading.entries] == ["T2 — the record format"]
    assert reading.discarded == (head, tail)


@pytest.mark.parametrize(
    "text",
    [
        "done\n- [2026-09-15T16:03-0300] done: a unit nobody did",   # forges a line
        f"a unit {SENTINEL} and more",                               # forges a completion
        "a unit [ev: commit:deadbeef]",                              # forges evidence
    ],
)
def test_render_refuses_text_that_would_forge_a_line_a_completion_or_evidence(text):
    """Mutation: delete the guards, or sanitise instead of raising.

    Text is free-form and arrives from an agent — the format's only injection surface. Each
    string here is *silently* well-formed once written: the first appears as two lines, the
    second as a complete line with a trailing comment, the third as a unit carrying evidence
    that was never checked. A refused line is visible; a forged one reads as a record.
    """
    with pytest.raises(ValueError):
        render("done", text, ts=_TS)


def test_the_row_adds_up_when_a_unit_ships_without_ever_being_declared():
    """Mutation: count `requested` from intent lines only.

    R2 makes the intent line optional — a unit *may* be declared before it is completed. Count
    only declared units and a session that shipped something it never declared renders
    `requested 1 · shipped 2`, a row that reads as nonsense on a path the spec allows. The
    invariant is `requested == shipped + len(lost)`, and it is the row's only arithmetic.
    """
    reading = read(
        _record(
            render("intent", "declared and shipped", ts=_TS),
            render("intent", "declared and lost", ts=_TS),
            render("done", "declared and shipped", evidence=["commit:3e2f42f"], ts=_TS),
            render("done", "shipped, never declared", evidence=["file:x.md"], ts=_TS),
        )
    )
    row = tally(reading.entries)

    assert (row.requested, row.shipped, row.lost) == (3, 2, ("declared and lost",))
    assert row.requested == row.shipped + len(row.lost)


def test_evidence_refs_survive_the_round_trip_and_a_comma_cannot_split_one():
    """Mutation: drop the `,` guard in `render`, or split the ev field on something else.

    The refs are joined with `", "` and split back on `","`, so a ref containing a comma would
    come back as two refs — two checks T3 would then run against two references that do not
    exist. Guarding at write time is what keeps the reader's split total.
    """
    line = render("done", "T3", evidence=["commit:3e2f42f", "file:out/report.md"], ts=_TS)
    assert parse(line).evidence == ("commit:3e2f42f", "file:out/report.md")

    with pytest.raises(ValueError):
        render("done", "T3", evidence=["file:a,b.md"], ts=_TS)
