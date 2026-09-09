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
