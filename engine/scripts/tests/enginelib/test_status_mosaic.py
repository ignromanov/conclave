"""The mosaic vocabulary: an instance-wide number assembled from per-key snapshots.

Every assertion here is about a conflation that a count-only implementation makes
silently. The union of five gh caches is not a measurement — it is five measurements
taken at five different moments, any of which may be missing — and the failure mode
is that it renders exactly like a measurement.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from enginelib.status.reduce import (
    MissingShard,
    Shard,
    combine_shards,
    worst_verdict,
)

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)


def _shard(key: str, *ids: str, ago: timedelta = timedelta(0)) -> Shard:
    return Shard(key=key, captured_at=NOW - ago, identities=ids)


def test_a_key_that_saw_nothing_is_not_a_key_that_never_looked():
    """The distinction the whole type exists for.

    `queue.collect` returns [] for a missing cache and for a cache holding zero
    items — measured, both real states on this instance today. If the mosaic cannot
    tell them apart, "the queue is empty" and "we never looked" print identically.
    """
    looked = combine_shards([_shard("a")])
    never = combine_shards([MissingShard(key="a", reason="снимок не снят")])

    assert looked.total == 0 and not looked.nothing_reported
    assert never.total == 0 and never.nothing_reported
    assert looked.reporting == ("a",) and never.reporting == ()


def test_identities_are_deduped_across_shards():
    """An issue with two advisor labels lands in two caches. Summing counts doubles it."""
    m = combine_shards([_shard("a", "r#1", "r#2"), _shard("b", "r#2", "r#3")])
    assert m.total == 3, "identities were summed instead of unioned"


def test_the_number_is_scoped_by_repo_not_by_issue_number():
    """Two repos, same issue number, different issues — dedup must not merge them."""
    m = combine_shards([_shard("a", "conclave#57"), _shard("b", "conclave-ai#57")])
    assert m.total == 2


def test_freshness_is_the_oldest_member_never_the_newest():
    """The measured defect: four caches refreshed at 21:51Z, one still at 19:56Z, and
    the issue created at 20:17Z appeared in none of them. Taking the newest capture
    would have called that union current."""
    m = combine_shards([
        _shard("fresh", "r#1", ago=timedelta(minutes=1)),
        _shard("stale", "r#2", ago=timedelta(hours=2)),
        _shard("fresh2", "r#3", ago=timedelta(minutes=2)),
    ])
    assert m.oldest == NOW - timedelta(hours=2)


def test_any_missing_key_makes_the_total_a_floor():
    m = combine_shards([_shard("a", "r#1"), MissingShard(key="b", reason="нет снимка")])
    assert m.is_floor
    assert m.total == 1
    assert [s.key for s in m.missing] == ["b"]


def test_a_complete_mosaic_is_not_a_floor():
    assert not combine_shards([_shard("a", "r#1"), _shard("b")]).is_floor


def test_an_empty_mosaic_reports_nothing_rather_than_zero():
    """No shards at all — an empty roster — must not read as a measured zero."""
    m = combine_shards([])
    assert m.nothing_reported and m.oldest is None


def test_missing_shard_refuses_a_blank_reason():
    """Same contract as Absent.reason: a gap with no words is rule-6 forbidden."""
    with pytest.raises(ValueError, match="reason is mandatory"):
        MissingShard(key="a", reason="  ")


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        (("fresh", "fresh"), "fresh"),
        (("fresh", "stale_warn"), "stale_warn"),
        (("stale_warn", "stale_error"), "stale_error"),
        # The one that is not severity-descending: uncertainty outranks known-bad.
        (("stale_error", "unknown"), "unknown"),
        (("unknown", "fresh"), "unknown"),
    ],
)
def test_worst_verdict_ranks_uncertainty_above_known_bad(verdicts, expected):
    assert worst_verdict(*verdicts) == expected


def test_worst_verdict_refuses_an_empty_argument_list():
    """Returning a default here would be a silent 'fresh' for a slot nobody judged."""
    with pytest.raises(ValueError, match="at least one"):
        worst_verdict()
