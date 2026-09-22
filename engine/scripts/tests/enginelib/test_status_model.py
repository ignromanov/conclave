"""The status projection's pure core (GH#57).

The tests that matter here are the ones asserting a thing CANNOT be expressed:
spec 115's rules 5, 6 and 7 each failed once as a printer convention, which is why
they are being moved into the type. A test that only checks the happy path would
pass against an `int | None` encoding too, and that encoding is the defect.

Throwaway slot names are rendered against `words(...)` — `EN` plus keys invented for
one test. That is not a convenience: it is the property under test in rule 10. A
printer that can render a catalog it does not ship is a printer whose language is the
surface's choice, and every test here that names a slot proves it again.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from enginelib.status.model import Absent, Count, Phrase, SectionResult, Staleness
from enginelib.status.reduce import (
    MAX_DEVIATION_CLUSTERS,
    deviations,
    measured_total,
    over_cluster_budget,
    rank_sections,
)
from enginelib.status.render_terminal import glance, quantity
from enginelib.status.words import EN

NOW = datetime(2026, 9, 9, 12, 0, 0)


def words(**extra: str) -> dict[str, str]:
    """The canonical catalog plus keys this test invented. See the module docstring."""
    return {**EN, **extra}


# --------------------------------------------------------------------------
# Rule 5 — a count carries its scope noun and its one-hop proof
# --------------------------------------------------------------------------


def test_count_refuses_a_bare_number() -> None:
    """"0/237" is a numeric bare identifier; the noun and the proof are not optional.

    Both are now `Phrase`, so the mandate is carried by the signature — omitting one
    is a TypeError rather than a validation branch — and the empty-string escape that
    validation existed to catch is closed one level down, in `Phrase` itself.
    """
    with pytest.raises(TypeError):
        Count(value=0, noun=Phrase("noun.feedback"))  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="key is mandatory"):
        Count(value=0, noun=Phrase("   "), proof=Phrase("proof.literal"))


def test_count_refuses_a_value_above_its_denominator() -> None:
    with pytest.raises(ValueError, match="exceeds its denominator"):
        Count(value=238, noun=Phrase("noun.feedback"), proof=Phrase("proof.literal"), of=237)


# --------------------------------------------------------------------------
# Rule 6 — absence is not zero, and it is not expressible without a reason
# --------------------------------------------------------------------------


def test_absent_refuses_a_missing_reason() -> None:
    """A bare em dash is 'the greyed-out chart in a new costume' — rule 6 forbids it."""
    with pytest.raises(TypeError):
        Absent()  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="key is mandatory"):
        Absent(reason=Phrase(""))


def test_measured_zero_and_absent_do_not_render_alike() -> None:
    """The whole point of the sum type. `if not count` must not be able to merge these."""
    catalog = words(**{"noun.records": "records resolved", "absent.never": "never ran"})
    zero = SectionResult(
        name=Phrase("slot.feedback"),
        measurement=Count(
            value=0, noun=Phrase("noun.records"), proof=Phrase("proof.literal"), of=237
        ),
    )
    never_ran = SectionResult(
        name=Phrase("slot.feedback"),
        measurement=Absent(reason=Phrase("absent.never")),
    )
    assert quantity(zero.measurement, words=catalog) == "0 of 237 records resolved"
    assert quantity(never_ran.measurement, words=catalog).startswith("— ")
    assert quantity(zero.measurement, words=catalog) != quantity(
        never_ran.measurement, words=catalog
    )


def test_glance_keeps_zero_rows() -> None:
    """Rule 3 + the zero-rows carve-out: on an inventory surface a zero IS the answer.

    The session-summary contract omits zero rows; this surface renders them, and the
    two contracts are scoped against each other explicitly. A printer that drops
    empties would silently import the wrong one.
    """
    catalog = words(**{
        "slot.blockers": "blockers", "noun.blockers": "blockers",
        "slot.specs2": "specs", "noun.specs2": "specs done",
    })
    sections = [
        SectionResult(
            Phrase("slot.blockers"),
            Count(0, Phrase("noun.blockers"), Phrase("proof.literal")),
        ),
        SectionResult(
            Phrase("slot.specs2"),
            Count(9, Phrase("noun.specs2"), Phrase("proof.literal")),
        ),
    ]
    block = glance("engine", "🦉", Phrase("surface.state"), "09.09", sections, catalog)
    assert "**blockers**  0 blockers" in block
    assert "**specs**  9 specs done" in block


def test_measured_total_is_none_when_nothing_was_measured() -> None:
    """A total of zero over zero instruments is exactly the conflation rule 6 forbids."""
    sections = [SectionResult(Phrase("slot.ci"), Absent(reason=Phrase("absent.ci")))]
    assert measured_total(sections) is None


# --------------------------------------------------------------------------
# Rule 7 — staleness is computed from last MOVEMENT, with two thresholds
# --------------------------------------------------------------------------


@pytest.fixture
def queue() -> Staleness:
    return Staleness(warn_after=timedelta(days=7), error_after=timedelta(days=14))


@pytest.mark.parametrize(
    ("days_since_movement", "expected"),
    [(0, "fresh"), (6, "fresh"), (7, "stale_warn"), (13, "stale_warn"), (14, "stale_error"),
     (400, "stale_error")],
)
def test_staleness_thresholds(queue: Staleness, days_since_movement: int, expected: str) -> None:
    moved = NOW - timedelta(days=days_since_movement)
    assert queue.assess(moved, NOW) == expected


def test_never_moved_is_unknown_not_stale(queue: Staleness) -> None:
    """A queue whose movement was never recorded and one that has not moved are
    different facts. Rule 6 applies to verdicts as much as to counts."""
    assert queue.assess(None, NOW) == "unknown"


def test_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        Staleness(warn_after=timedelta(days=14), error_after=timedelta(days=7))


# --------------------------------------------------------------------------
# Rule 2 — uncertainty outranks known-bad; four clusters is the cap
# --------------------------------------------------------------------------


def _row(key: str, **kw: object) -> SectionResult:
    return SectionResult(
        Phrase(key), Count(1, Phrase("noun.feedback"), Phrase("proof.literal")), **kw  # type: ignore[arg-type]
    )


def test_unknown_outranks_error() -> None:
    """Icinga's convention, and the one a printer author reliably gets backwards:
    'we cannot tell' is more urgent than 'we know it is degraded'."""
    sections = [
        _row("c", verdict="fresh"),
        _row("b", verdict="stale_error"),
        SectionResult(Phrase("a"), Absent(reason=Phrase("absent.ci")), verdict="unknown"),
        _row("d", verdict="stale_warn"),
    ]
    assert [s.name.key for s in rank_sections(sections)] == ["a", "b", "d", "c"]


def test_rank_is_stable_on_ties() -> None:
    """Fixed positions let a repeat reader diff against memory; an unstable sort
    destroys that invisibly."""
    sections = [_row("zebra", verdict="stale_warn"), _row("alpha", verdict="stale_warn")]
    assert [s.name.key for s in rank_sections(sections)] == ["alpha", "zebra"]
    assert [s.name.key for s in rank_sections(list(reversed(sections)))] == ["alpha", "zebra"]


def test_ties_break_on_the_key_not_on_the_worded_label() -> None:
    """The report's order must not change with the operator's language.

    Mutation: sort by the rendered name instead of `name.key` and this reddens — the
    two slots below sort one way by key and the opposite way by every word any catalog
    could give them. A reader who switched language would otherwise see a reshuffled
    report and no change in a single fact, which is rule 2's fixed positions lost to a
    setting that changes nothing measurable.
    """
    sections = [_row("alpha", verdict="fresh"), _row("beta", verdict="fresh")]
    assert [s.name.key for s in rank_sections(sections)] == ["alpha", "beta"]

    catalog = words(**{"alpha": "zzz", "beta": "aaa"})
    block = glance("engine", "🦉", Phrase("surface.state"), "09.09", sections, catalog)
    assert block.index("**zzz**") < block.index("**aaa**")


def test_clean_sections_are_not_deviations() -> None:
    sections = [
        SectionResult(
            Phrase("ok"),
            Count(0, Phrase("noun.feedback"), Phrase("proof.literal")),
            verdict="fresh",
        )
    ]
    assert deviations(sections) == []


def test_cluster_budget_fires_above_four() -> None:
    def dev(n: int) -> SectionResult:
        return _row(f"s{n}", severity="warn")

    assert not over_cluster_budget([dev(i) for i in range(MAX_DEVIATION_CLUSTERS)])
    assert over_cluster_budget([dev(i) for i in range(MAX_DEVIATION_CLUSTERS + 1)])


# --------------------------------------------------------------------------
# Rule 7b — the deviation set is `Absent` ∪ content-bad, never staleness
# --------------------------------------------------------------------------


def test_stale_reading_is_not_a_deviation() -> None:
    """The measurement that took the budget from 1 to 5 on the live projection.

    Four of the five 'deviations' on 2026-09-19 were stale reads of slots with nothing
    wrong in them. Grouping them — which rule 2 prescribes on a breach — would have
    produced a tidy surface that was wrong in a new way, so the remedy was the set,
    not the grouping.
    """
    stale = [
        _row(f"s{n}", verdict="stale_error")
        for n in range(MAX_DEVIATION_CLUSTERS + 3)
    ]
    assert deviations(stale) == []
    assert not over_cluster_budget(stale)


def test_absent_is_always_a_deviation() -> None:
    """Ruling 1: an instrument that never ran is a fact about the system, not about
    the reading's age — so it survives the split even with no severity set."""
    section = SectionResult(
        Phrase("slot.ci"), Absent(reason=Phrase("absent.ci")), verdict="unknown"
    )
    assert section.severity is None
    assert deviations([section]) == [section]


def test_unjudged_section_is_not_a_deviation() -> None:
    """`severity is None` means nobody judged the slot. That is a third state, and
    reading it as a finding would manufacture deviations out of silence."""
    assert deviations([_row("slot.queue")]) == []
