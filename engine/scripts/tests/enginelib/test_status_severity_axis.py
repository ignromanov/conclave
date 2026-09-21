"""Two axes, two carriers: content takes the glyph, freshness takes words (rules 7a/7b).

Every assertion here pins a half of one defect that survived ten days in review and
however long before that, because **each half reads correctly on its own**. Live on
2026-09-19:

    ▍ ✗ **p0**  0 p0-блокеров по инстансу
    ▍ **фидбек**  131 из 489 фидбек-записей resolved

The first row is the best state that slot can hold, wearing the blocking glyph, because
a gh snapshot was ~19 hours old. The second carries no glyph at all, because its index
was written recently — not because 27 % resolved is fine. Neither glyph is about what
its number says, and nothing on either row tells the reader that.

The cause was one enum: `Verdict` is `fresh | stale_warn | stale_error | unknown`, every
member a statement about TIME, mapped by the printer onto a glyph set
`output-formatting.md` §2 defines as content severity.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from enginelib.status.branches import BranchRow, section_severity
from enginelib.status.model import Absent, Count, Freshness, SectionResult
from enginelib.status.reduce import worst_severity
from enginelib.status.render_terminal import freshness_suffix, glance, mark, quantity


def _count(value: int = 0, noun: str = "p0-блокеров по инстансу") -> Count:
    return Count(value=value, noun=noun, proof="union agent-memory/gh-cache/*.md")


# --------------------------------------------------------------------------
# The failing render, restored
# --------------------------------------------------------------------------


def test_a_clean_slot_read_from_a_stale_snapshot_wears_no_blocking_glyph() -> None:
    """The exact row from 2026-09-19, rebuilt: zero p0 blockers, 19-hour-old snapshot.

    Before rules 7a/7b this printed `✗ **p0**  0 p0-блокеров по инстансу`. The glyph
    came from `worst_verdict` over two staleness axes and said nothing whatever about
    the zero it was standing next to.
    """
    section = SectionResult(
        name="p0",
        measurement=_count(0),
        verdict="stale_warn",
        severity="ok",
        freshness=(Freshness(axis="snapshot", verdict="stale_warn", age=timedelta(hours=19)),),
    )
    rendered = glance("engine", "🦉", "состояние", "19.09", [section])

    assert "✗" not in rendered
    assert "⚠" not in rendered
    # The age did not disappear; it changed carrier, which is what rule 7 asked for
    # in the first place ("age renders beside the verdict as evidence").
    assert "· снимку 19ч" in rendered


def test_the_age_is_evidence_even_when_the_content_is_bad() -> None:
    """Both axes at once, each in its own carrier — the case that proves they are
    independent rather than merely reordered."""
    section = SectionResult(
        name="p0",
        measurement=_count(3),
        verdict="stale_error",
        severity="error",
        freshness=(Freshness(axis="snapshot", verdict="stale_error", age=timedelta(days=2)),),
    )
    rendered = glance("engine", "🦉", "состояние", "19.09", [section])

    assert "✗ **p0**" in rendered
    assert "· снимку 2д" in rendered


# --------------------------------------------------------------------------
# The glyph column — content severity, `Absent`, and the third state
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("severity", "glyph"),
    [("error", "✗ "), ("warn", "⚠ "), ("ok", ""), (None, "")],
)
def test_glyph_comes_from_severity(severity, glyph) -> None:
    assert mark(SectionResult("s", _count(1), severity=severity)) == glyph


def test_an_instrument_that_never_ran_keeps_its_warning() -> None:
    """Ruling 1, and the one case where the glyph does not come from `severity`.

    An unwired slot has no content to be severe about, so `severity` is `None` — and
    reading the glyph off `severity` alone would have silently un-flagged every
    `Absent` row on the surface. Absence is a fact about the system, not about the
    reading's age.
    """
    section = SectionResult("CI", Absent(reason="не подключено"), verdict="unknown")
    assert section.severity is None
    assert mark(section) == "⚠ "


def test_staleness_cannot_reach_the_glyph_by_any_route() -> None:
    """The mutation that matters: set every staleness field to its worst value and
    leave the content judgment clean. Nothing in the glyph column may move."""
    for verdict in ("fresh", "stale_warn", "stale_error", "unknown"):
        section = SectionResult(
            name="очередь",
            measurement=_count(162, "issue открыто по инстансу"),
            verdict=verdict,
            severity="ok",
        )
        assert mark(section) == "", f"{verdict} reached the glyph column"


# --------------------------------------------------------------------------
# The words a stale reading carries instead
# --------------------------------------------------------------------------


def test_each_axis_words_itself() -> None:
    """`snapshot` and `movement` are not interchangeable: a queue read every session
    and moved by nobody is fresh on the first and dead on the second (rule 7)."""
    suffix = freshness_suffix((
        Freshness(axis="snapshot", verdict="stale_warn", age=timedelta(hours=19)),
        Freshness(axis="movement", verdict="stale_error", age=timedelta(days=12)),
    ))
    assert suffix == " · снимку 19ч · очередь не двигалась 12д"


def test_a_fresh_axis_says_nothing() -> None:
    """A suffix on a current reading is noise. The reader is being handed a reason to
    discount a number, not a timestamp."""
    assert freshness_suffix((Freshness(axis="snapshot", verdict="fresh", age=timedelta(0)),)) == ""


def test_an_axis_that_could_not_be_evaluated_says_so_in_words() -> None:
    """Rule 6 on the freshness axis: 'we could not tell when' and 'it is current' must
    never render alike."""
    suffix = freshness_suffix((Freshness(axis="movement", verdict="unknown"),))
    assert suffix == " · движение не зафиксировано"


def test_an_age_under_an_hour_is_not_rendered_as_zero() -> None:
    """`0ч` would read as 'no age', which is the absence-vs-zero conflation in
    miniature — on the very surface written to forbid it."""
    suffix = freshness_suffix((
        Freshness(axis="snapshot", verdict="stale_warn", age=timedelta(minutes=20)),
    ))
    assert suffix == " · снимку 1ч"


def test_quantity_carries_the_suffix_so_every_printer_inherits_it() -> None:
    """B3: the wording lives in `quantity` — already the one place it lives — so a
    second printer over this projection gets the split rather than re-deriving it."""
    text = quantity(
        _count(131, "фидбек-записей resolved"),
        (Freshness(axis="snapshot", verdict="stale_warn", age=timedelta(hours=3)),),
    )
    assert text == "131 фидбек-записей resolved · снимку 3ч"


# --------------------------------------------------------------------------
# The model's own guards
# --------------------------------------------------------------------------


def test_freshness_refuses_an_age_it_could_not_have_measured() -> None:
    """`unknown` means the axis could not be evaluated, so it has no age; inventing
    `timedelta(0)` for it is `Absent`-vs-`Count(0)` one level down."""
    with pytest.raises(ValueError, match="present exactly when"):
        Freshness(axis="snapshot", verdict="unknown", age=timedelta(hours=1))


def test_freshness_refuses_a_measured_axis_with_no_age() -> None:
    with pytest.raises(ValueError, match="present exactly when"):
        Freshness(axis="snapshot", verdict="stale_warn")


# --------------------------------------------------------------------------
# The branch slot — the one builder rule 7a names as having a real threshold
# --------------------------------------------------------------------------


def _branch(disposition: str, *, stale_ref: bool = False) -> BranchRow:
    return BranchRow(
        name=f"b-{disposition}",
        disposition=disposition,
        reason="fixture",
        stale_tracking_ref=stale_ref,
    )


def test_a_branch_requiring_action_is_a_deviation_by_definition() -> None:
    """Rule 7a's own example of a defensible threshold. `shipped` means the work is
    upstream and the branch is residue — something for the operator to do."""
    assert section_severity([_branch("shipped")]) == "warn"
    assert section_severity([_branch("unproposed")]) == "warn"
    assert section_severity([_branch("inspect")]) == "warn"


def test_commits_on_top_of_a_merged_pr_are_the_error_case() -> None:
    """The one shape that loses work if the branch is cleaned up on the strength of
    'its PR merged' — so it outranks every other disposition."""
    rows = [_branch("shipped"), _branch("beyond_merge"), _branch("in_flight")]
    assert section_severity(rows) == "error"


def test_a_false_fact_in_the_local_repo_outranks_every_disposition() -> None:
    """A tracking ref pointing at a branch the server no longer holds is not a
    gradient — a push silently acts on it."""
    assert section_severity([_branch("in_flight", stale_ref=True)]) == "error"


def test_quiet_branches_are_judged_ok_and_not_unjudged() -> None:
    """`ok` and not `None`: this slot HAS a threshold, so 'we looked and there was
    nothing to act on' is a judgment — which rule 3 wants stated, not implied."""
    assert section_severity([_branch("in_flight"), _branch("fresh_start")]) == "ok"
    assert section_severity([]) == "ok"


def test_the_branch_slot_carries_no_freshness_axis() -> None:
    """`for-each-ref` and `ls-remote` are read live. There is no snapshot whose age a
    reader would discount, so a suffix here would be inventing evidence."""
    section = SectionResult("ветки", _count(2, "веток требуют действия"), severity="warn")
    assert section.freshness == ()
    assert quantity(section.measurement, section.freshness) == "2 веток требуют действия"


def test_worst_severity_never_turns_silence_into_a_verdict() -> None:
    """`None` is the absence of a judgment: it loses to any real one and survives only
    when there is no other. A `max()` over a set containing it does the opposite."""
    assert worst_severity(None, None) is None
    assert worst_severity(None, "ok") == "ok"
    assert worst_severity("ok", "warn") == "warn"
    assert worst_severity("warn", "error", None) == "error"
    assert worst_severity() is None
