"""status/model.py — the shape of one state projection. I/O-free.

Spec 115 (`state-report.md`) rule 11 names three printers over one canonical model:
the terminal render, the 102 dashboard, and `engine status` (GH#57). This module is
that model's vocabulary. It performs no I/O and imports nothing from `briefing/` —
the sanctioned edge runs briefing -> enginelib, and GH#106 exists because six edges
already run the other way.

The design pressure is rule 6: "a measured zero renders 0; an instrument that never
ran renders — plus a mandatory reason in words. The two must never render alike."

The obvious encoding is `int | None`, with None for absent. It is also the SQL-NULL
trap the rule is written against: two states share one field, and the first
`if not count:` in any printer collapses them. Every printer would have to remember
the distinction, and printers are exactly where this contract has already failed once.

So absence is a separate type, and `Absent` cannot be constructed without its reason.
A printer that wants to conflate them has to work at it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal


@dataclass(frozen=True)
class Count:
    """A number that carries what it counts and where to check it.

    Rule 5: "0/237" is a numeric bare identifier. A count renders as
    "0 of 237 feedback records resolved", and the work section behind it names the
    file or command that reproduces the number.

    Both fields are required because both were missing from the report that failed.
    """

    value: int
    noun: str
    proof: str
    of: int | None = None

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(f"Count.value is a cardinality, got {self.value}")
        if not self.noun.strip():
            raise ValueError("Count.noun is mandatory — a bare number is rule-5 noise")
        if not self.proof.strip():
            raise ValueError("Count.proof is mandatory — every count is one hop from its source")
        if self.of is not None and self.value > self.of:
            raise ValueError(f"Count {self.value} exceeds its denominator {self.of}")


@dataclass(frozen=True)
class Absent:
    """The instrument did not run. Distinct from a measured zero, by type.

    `reason` is mandatory and is prose for a human: rule 6 rejects a bare em dash as
    "the greyed-out chart in a new costume".
    """

    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError(
                "Absent.reason is mandatory — '—' with no reason clause is rule-6 forbidden"
            )


# A slot either measured something or did not. There is no third value, and no
# in-band sentinel: `Measurement` is the only way to say "no number here".
Measurement = Count | Absent


Verdict = Literal["fresh", "stale_warn", "stale_error", "unknown"]


@dataclass(frozen=True)
class Staleness:
    """Two thresholds over a queue's last MOVEMENT — never its last read.

    Rule 7 puts the whole defect in one word. A queue that is read every session and
    moved never is fresh by read-time and dead by movement-time; the read-time answer
    is the one that makes a stalled queue invisible, which is the state this instance
    was in when the rule was written. The parameter is named `last_movement` so a
    caller passing a read timestamp has to mislabel it on purpose.
    """

    warn_after: timedelta
    error_after: timedelta

    def __post_init__(self) -> None:
        if self.warn_after > self.error_after:
            raise ValueError(
                f"warn_after ({self.warn_after}) must not exceed error_after ({self.error_after})"
            )

    def assess(self, last_movement: datetime | None, now: datetime) -> Verdict:
        """Classify a queue by how long since it last MOVED.

        `last_movement=None` is `unknown`, not `stale`: a queue whose movement was
        never recorded and a queue that has not moved are different facts, and rule 6
        applies to verdicts as much as to counts.
        """
        if last_movement is None:
            return "unknown"
        age = now - last_movement
        if age >= self.error_after:
            return "stale_error"
        if age >= self.warn_after:
            return "stale_warn"
        return "fresh"


@dataclass(frozen=True)
class SectionResult:
    """One named slot of the projection: its measurement, its rows, its freshness.

    `name` is the join between the two layers of the render — the glance row and the
    work section carry the same name, in the same order, so the glance block is the
    table of contents (state-report.md §Shape).
    """

    name: str
    measurement: Measurement
    verdict: Verdict = "fresh"
    rows: tuple[object, ...] = ()

    @property
    def measured(self) -> bool:
        return isinstance(self.measurement, Count)
