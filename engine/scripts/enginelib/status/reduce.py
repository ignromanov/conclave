"""status/reduce.py — the arithmetic every printer must agree on. I/O-free, pure.

Three printers render this projection (spec 115 rule 11). Anything they could each
get subtly wrong belongs here once, not three times. Two rules qualify:

* **Ordering.** Rule 2 ranks uncertainty ABOVE known-bad within a slot — "we cannot
  tell" is more urgent than "we know it is degraded" (the Icinga convention:
  UNKNOWN before WARNING). Left to a printer author, the intuitive order is
  severity-descending, which buries exactly the rows that need a human.
* **Cluster budget.** Rule 2 caps a report at four deviation clusters (Cowan 4±1).
  More findings than that are GROUPED, never flattened — a wall of rows restores
  the illegibility the contract was written against.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from enginelib.status.model import Count, SectionResult, Verdict

# Rank order, most urgent first. `unknown` leads deliberately — see module docstring.
_VERDICT_RANK: dict[Verdict, int] = {
    "unknown": 0,
    "stale_error": 1,
    "stale_warn": 2,
    "fresh": 3,
}

# Rule 2: at most four deviation clusters in one report.
MAX_DEVIATION_CLUSTERS = 4


def rank_sections(sections: Iterable[SectionResult]) -> list[SectionResult]:
    """Sections ordered by urgency, ties broken by name so the render is stable.

    Stability matters more than it looks: rule 2 wants fixed positions so a repeat
    reader can diff against memory. A sort that reorders equal-verdict rows between
    runs destroys that, and it does it invisibly.
    """
    return sorted(sections, key=lambda s: (_VERDICT_RANK[s.verdict], s.name))


def worst_verdict(*verdicts: Verdict) -> Verdict:
    """The most urgent of several verdicts about one slot.

    A slot can be judged on more than one axis at once — the gh queue is judged both
    on when it last MOVED (rule 7) and on how old the snapshot showing that movement
    is. Combining them by hand invites the same mistake in each printer, and the
    intuitive combination (take the most recent, take the average) is the one that
    hides a problem. `unknown` wins every tie because rule 2 ranks it first: an axis
    that could not be evaluated makes the whole slot uncertain, and uncertainty
    outranks a known-bad reading.
    """
    if not verdicts:
        raise ValueError("worst_verdict needs at least one verdict")
    return min(verdicts, key=lambda v: _VERDICT_RANK[v])


def deviations(sections: Iterable[SectionResult]) -> list[SectionResult]:
    """The sections a reader must act on: anything not `fresh`, ranked.

    An unmeasured section is a deviation even when nothing is known to be wrong —
    that is rule 6 carried into the ordering. A section that measured cleanly is not
    a deviation, but it is still reported (rule 3: success is stated, never implied);
    the caller renders it, this function just does not rank it as a problem.
    """
    return [s for s in rank_sections(sections) if s.verdict != "fresh"]


def over_cluster_budget(sections: Iterable[SectionResult]) -> bool:
    """True when the deviations exceed the four-cluster cap and must be grouped."""
    return len(deviations(sections)) > MAX_DEVIATION_CLUSTERS


def measured_total(sections: Iterable[SectionResult]) -> Count | None:
    """Sum of the measured sections, or None when nothing was measured.

    Returns None rather than `Count(0, ...)` on an all-absent projection: a total of
    zero over zero instruments is the exact conflation rule 6 forbids, and the caller
    that wants to say "nothing ran" should say so in words.
    """
    counts = [s.measurement for s in sections if isinstance(s.measurement, Count)]
    if not counts:
        return None
    return Count(
        value=sum(c.value for c in counts),
        noun="across measured sections",
        proof="derived: sum of this projection's measured sections",
    )


# ---------------------------------------------------------------------------
# Mosaics — an instance-wide number assembled from per-key snapshots
# ---------------------------------------------------------------------------
#
# Some sources are not one measurement. The gh queue is five per-advisor caches,
# each written by its own `gh-fetch` at its own moment, and "the instance's open
# queue" is their union. That union is not a measurement either — it is a mosaic,
# and it fails in two ways a single count cannot:
#
#   1. Its members have different ages. Measured 2026-09-09: four caches refreshed
#      at 21:51Z by session-init, one (forge-chro) still at 19:56Z; GH#250 was
#      created at 20:17Z and appears in NONE of them. The union said 137, the repo
#      held 138. Four fresh members hid the one stale member, and the number looked
#      authoritative. A mosaic's freshness is therefore its OLDEST member's, never
#      its newest and never an average.
#   2. A member can be missing outright — an advisor whose cache was never fetched.
#      Skipping it silently turns the total into a floor that is presented as a
#      total, which is rule 6's conflation wearing a different hat.


@dataclass(frozen=True)
class Shard:
    """One key's contribution to a mosaic: what it saw, and when it looked.

    `identities` are opaque stable strings (e.g. "conclave#249") rather than counts,
    because a mosaic must DEDUPE: an issue carrying two advisor labels lands in two
    caches, and summing counts would report it twice. Measured on this instance:
    0 of 137 issues appear in more than one cache today — which is exactly why a
    count-summing implementation would pass every test written against live data
    and start double-counting on the first two-label issue anyone files.
    """

    key: str
    captured_at: datetime
    identities: tuple[str, ...]


@dataclass(frozen=True)
class MissingShard:
    """A key that contributed nothing because its source was not there.

    Distinct from `Shard(identities=())`, which is a key that looked and saw zero.
    Same distinction as `Absent` vs `Count(0)`, one level down, and it exists here
    for the same reason: the printer must not be the thing that remembers.
    """

    key: str
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("MissingShard.reason is mandatory — see Absent.reason")


@dataclass(frozen=True)
class Mosaic:
    """The union of a mosaic's shards, with the two facts a printer needs to be honest."""

    total: int
    oldest: datetime | None
    reporting: tuple[str, ...]
    missing: tuple[MissingShard, ...]

    @property
    def is_floor(self) -> bool:
        """True when at least one key did not report, so `total` understates.

        The word is the one `queue.py` already uses for a truncated snapshot:
        "the count above is a floor, not the queue".
        """
        return bool(self.missing)

    @property
    def nothing_reported(self) -> bool:
        """True when no key reported at all — the mosaic measured nothing.

        The caller renders this as `Absent`, not as a zero. A mosaic of five missing
        caches and a mosaic of five empty caches are different facts about the
        instance, and only the second one is "the queue is empty".
        """
        return not self.reporting


def combine_shards(shards: Iterable[Shard | MissingShard]) -> Mosaic:
    """Union the shards, dedupe by identity, and age the result by its oldest member."""
    seen: set[str] = set()
    reporting: list[str] = []
    missing: list[MissingShard] = []
    oldest: datetime | None = None

    for shard in shards:
        if isinstance(shard, MissingShard):
            missing.append(shard)
            continue
        reporting.append(shard.key)
        seen.update(shard.identities)
        if oldest is None or shard.captured_at < oldest:
            oldest = shard.captured_at

    return Mosaic(
        total=len(seen),
        oldest=oldest,
        reporting=tuple(reporting),
        missing=tuple(missing),
    )
