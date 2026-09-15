"""A record the engine wrote must still say what it was given.

#249 item 1: nothing validates a record after it is written. The engine's readers are
line-based on purpose, so a record whose YAML value is gone reads correctly everywhere
the engine looks — `sessions/2026-09-14-sage-cto-117-mechanism-decided.md` carries
`issues: [#26]`, does not parse, and its reflexion still rendered in session-init's
banner the next morning.

The predicate here is LOSS, not disagreement between the two readers. They disagree
constantly and harmlessly: `created: 2026-09-15T02:19:42-03:00` is a string to one and a
`datetime` to the other — a different type carrying the same information. A first pass
written as "report every difference" flagged 32 of 30 mention records, which is a gate
nobody would read twice.

Loss has exactly two shapes, both produced by `#`:
  value becomes None      — a leading `#` commented the whole value out (#301)
  value becomes a PREFIX  — a mid-value ` #` ate the tail (5 session reflexions)
"""
from __future__ import annotations

import pytest

from enginelib import records

_OK = """advisor: sage-cto
date: 2026-09-15
issues: [250,251]
created: 2026-09-15T02:19:42-03:00
handoff:
reflexion: |-
  Ruled: the floor stays at 3.11, because 3.11 was the only interpreter reporting it.
"""


def test_a_clean_record_reports_nothing():
    """The paired assertion for every test below: a checker that reports everything
    would satisfy them all. Reddens under: reporting unconditionally.
    """
    assert records.find_lost_values(_OK) == []


# --- the two shapes of loss ---------------------------------------------------------

def test_a_leading_hash_value_is_reported_as_lost():
    """`ref_issue: #297` — a VALID document whose value is None. Reddens under: dropping
    the `is None` arm.
    """
    found = records.find_lost_values("ref_issue: #297\n")
    assert len(found) == 1 and "ref_issue" in found[0]


def test_a_truncated_value_is_reported():
    """` #` mid-value opens a comment and the tail is dropped with no error at all — the
    quietest of the three hazards and the one that cost five reflexions.

    Reddens under: dropping the prefix arm.
    """
    found = records.find_lost_values("note: fixed by #68; the index was right\n")
    assert len(found) == 1 and "note" in found[0]


def test_an_unparseable_record_is_reported():
    """The loud half — this is what `issues: [#26]` does. Reddens under: letting the
    parse error escape, or swallowing it.
    """
    found = records.find_lost_values("issues: [#26]\n")
    assert len(found) == 1 and "parse" in found[0].lower()


# --- what must NOT be reported ------------------------------------------------------

def test_a_timestamp_is_not_a_finding():
    """The false positive that would have made this gate noise. Reddens under: comparing
    the two readers for equality instead of for loss.
    """
    assert records.find_lost_values("created: 2026-09-15T02:19:42-03:00\n") == []


def test_a_legitimately_transformed_string_is_not_a_finding():
    """A double-quoted scalar with an escape parses to text the raw line does not equal —
    a real transformation that loses nothing. This is the test the timestamp case could
    not be: a `datetime` never reaches the string arm at all, so it cannot pin what that
    arm does.

    Reddens under: reporting whenever the parsed string differs from the written one,
    instead of only when it is a PREFIX of it.
    """
    assert records.find_lost_values('note: "line one\\nline two"\n') == []


def test_a_flow_list_is_not_a_finding():
    """`issues: [250,251]` is the shape most of the corpus carries. Reddens under:
    treating any non-string value as lost.
    """
    assert records.find_lost_values("issues: [250,251]\n") == []


def test_a_block_scalar_is_not_a_finding():
    """`reflexion: |-` plus an indented body. The line-based reader sees "|-" here and is
    simply the wrong reader; comparing it to the value would measure the instrument.

    Reddens under: comparing the block indicator against the parsed value.
    """
    assert records.find_lost_values("reflexion: |-\n  Ruled: yes, and no.\n") == []


def test_a_deliberately_empty_field_is_not_a_finding():
    """`handoff:` with no value is how the writer records "no handoff". Reddens under:
    reporting every key whose parsed value is None.
    """
    assert records.find_lost_values("handoff:\nduration_estimate:\n") == []


def test_a_quoted_hazard_is_not_a_finding():
    """The repaired form. Reddens under: comparing the parsed value to the raw line
    without removing the quotes that make it parse.
    """
    assert records.find_lost_values("ref_issue: '#297'\n") == []


# --- the writer cannot emit one ------------------------------------------------------

def test_render_record_refuses_to_write_a_record_that_lost_a_value(tmp_path):
    """Serialization is the fix; this is the verification of it. A template edit, or a
    caller handing in a wrongly-built `Raw`, must not get past the writer silently.

    Reddens under: removing the self-check from `render_record`.
    """
    from enginelib import frontmatter
    tpl = tmp_path / "t.md"
    tpl.write_text("---\nref_issue: {{ref}}\n---\n\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ref_issue"):
        frontmatter.render_record(tpl, {"ref": frontmatter.Raw("#297")})


def test_render_record_writes_a_correctly_serialized_record(tmp_path):
    """Paired: a self-check that rejected everything would satisfy the test above."""
    from enginelib import frontmatter
    tpl = tmp_path / "t.md"
    tpl.write_text("---\nref_issue: {{ref}}\n---\n\nbody\n", encoding="utf-8")
    assert "ref_issue: '#297'" in frontmatter.render_record(tpl, {"ref": "#297"})
