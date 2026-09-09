"""The status projection's pure core (GH#57).

The tests that matter here are the ones asserting a thing CANNOT be expressed:
spec 115's rules 5, 6 and 7 each failed once as a printer convention, which is why
they are being moved into the type. A test that only checks the happy path would
pass against an `int | None` encoding too, and that encoding is the defect.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from enginelib.status.model import Absent, Count, SectionResult, Staleness
from enginelib.status.reduce import (
    MAX_DEVIATION_CLUSTERS,
    deviations,
    measured_total,
    over_cluster_budget,
    rank_sections,
    tally,
)

NOW = datetime(2026, 9, 9, 12, 0, 0)


# --------------------------------------------------------------------------
# Rule 5 — a count carries its scope noun and its one-hop proof
# --------------------------------------------------------------------------


def test_count_refuses_a_bare_number() -> None:
    """"0/237" is a numeric bare identifier; the noun and the proof are not optional."""
    with pytest.raises(ValueError, match="noun is mandatory"):
        Count(value=0, noun="   ", proof="index.jsonl")
    with pytest.raises(ValueError, match="proof is mandatory"):
        Count(value=0, noun="feedback records resolved", proof="")


def test_count_refuses_a_value_above_its_denominator() -> None:
    with pytest.raises(ValueError, match="exceeds its denominator"):
        Count(value=238, noun="resolved", proof="index.jsonl", of=237)


# --------------------------------------------------------------------------
# Rule 6 — absence is not zero, and it is not expressible without a reason
# --------------------------------------------------------------------------


def test_absent_refuses_a_missing_reason() -> None:
    """A bare em dash is 'the greyed-out chart in a new costume' — rule 6 forbids it."""
    with pytest.raises(ValueError, match="reason is mandatory"):
        Absent(reason="")


def test_measured_zero_and_absent_do_not_render_alike() -> None:
    """The whole point of the sum type. `if not count` must not be able to merge these."""
    zero = SectionResult(
        name="feedback",
        measurement=Count(value=0, noun="records resolved", proof="_index/index.jsonl", of=237),
    )
    never_ran = SectionResult(
        name="triage",
        measurement=Absent(reason="не шёл ни разу (last-triage пуст)"),
    )
    rendered = dict(tally([zero, never_ran]))
    assert rendered["feedback"] == "0 of 237 records resolved"
    assert rendered["triage"].startswith("— ")
    assert rendered["feedback"] != rendered["triage"]


def test_tally_keeps_zero_rows() -> None:
    """Rule 3 + the zero-rows carve-out: on an inventory surface a zero IS the answer.

    The session-summary contract omits zero rows; this surface renders them, and the
    two contracts are scoped against each other explicitly. A tally that drops empties
    would silently import the wrong one.
    """
    sections = [
        SectionResult("blockers", Count(0, "blockers", "gh pr list")),
        SectionResult("specs", Count(9, "specs done", "REGISTRY.md")),
    ]
    assert [n for n, _ in tally(sections)] == ["blockers", "specs"]


def test_measured_total_is_none_when_nothing_was_measured() -> None:
    """A total of zero over zero instruments is exactly the conflation rule 6 forbids."""
    sections = [SectionResult("a", Absent(reason="not wired yet"))]
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


def test_unknown_outranks_error() -> None:
    """Icinga's convention, and the one a printer author reliably gets backwards:
    'we cannot tell' is more urgent than 'we know it is degraded'."""
    sections = [
        SectionResult("c", Count(1, "x", "p"), verdict="fresh"),
        SectionResult("b", Count(1, "x", "p"), verdict="stale_error"),
        SectionResult("a", Absent(reason="never ran"), verdict="unknown"),
        SectionResult("d", Count(1, "x", "p"), verdict="stale_warn"),
    ]
    assert [s.name for s in rank_sections(sections)] == ["a", "b", "d", "c"]


def test_rank_is_stable_on_ties() -> None:
    """Fixed positions let a repeat reader diff against memory; an unstable sort
    destroys that invisibly."""
    sections = [
        SectionResult("zebra", Count(1, "x", "p"), verdict="stale_warn"),
        SectionResult("alpha", Count(1, "x", "p"), verdict="stale_warn"),
    ]
    assert [s.name for s in rank_sections(sections)] == ["alpha", "zebra"]
    assert [s.name for s in rank_sections(list(reversed(sections)))] == ["alpha", "zebra"]


def test_clean_sections_are_not_deviations() -> None:
    sections = [SectionResult("ok", Count(0, "problems", "gh"), verdict="fresh")]
    assert deviations(sections) == []


def test_cluster_budget_fires_above_four() -> None:
    def dev(n: int) -> SectionResult:
        return SectionResult(f"s{n}", Count(1, "x", "p"), verdict="stale_warn")

    assert not over_cluster_budget([dev(i) for i in range(MAX_DEVIATION_CLUSTERS)])
    assert over_cluster_budget([dev(i) for i in range(MAX_DEVIATION_CLUSTERS + 1)])
