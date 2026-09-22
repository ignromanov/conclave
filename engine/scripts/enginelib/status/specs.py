"""status/specs.py — what a spec's acceptance block can and cannot say. I/O-free.

Plan 057 T10's first slot. The projection it feeds answers "what is going on with the
specs", and the reason it needs a module of its own is that **the honest answer is not
a number of done specs** — it is a partition, and three of its four parts are states of
the INSTRUMENT rather than states of the work.

The case that decided the shape, measured 2026-09-15 on this instance: spec 109 was
finished in full and every reader believed it open for 37 days. Its plan declared no
`verify:` predicate, so the scan could emit only `unverifiable`, and two advisors read
`unverifiable` as not-done — in a ranking, twice in one night. A gauge that cannot
report a state reports absence, and a reader converts absence into zero.

The same collapse is live in the spec corpus and larger. Of 31 specs here:

    measured        8    an acceptance block with checkboxes — N of M
    no_checkboxes  11    acceptance declared, nothing listed under it
    no_acceptance   9    no acceptance heading at all
    unowned         3    no ownership field, so the ownership filter drops it first

Twelve of thirty-one (39%) render in NO spec projection today and nothing says so.
`spec_progress.build` returns a line per spec it can speak about and simply omits the
rest, which is rule 6's forbidden state one step worse than a bare em dash: not
"absence rendered as zero" but absence rendered as nothing at all.

So `classify` is total — every spec lands in exactly one class, including the classes
that exist because the instrument failed — and `tally` counts all four. A caller that
wants only the speakable ones has to say so, which is the property `build` had by
accident and now has on purpose.

Pure by construction: the caller parses the file and hands over what it read. Nothing
here opens a path, so the same classification serves the briefing, `engine status`,
and the 102 dashboard without any of them re-deriving it (rule 11, one model).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

# Ordered from "the instrument spoke" to "the instrument never saw it". The order is
# load-bearing: `classify` returns the FIRST failure encountered reading the file, so a
# spec that is both unowned and blockless is `unowned` — the earlier gate is the one
# that actually dropped it, and reporting the later one would name a cause that never
# ran.
AcceptanceClass = Literal["measured", "no_checkboxes", "no_acceptance", "unowned"]

#: Classes in which the spec's acceptance state is NOT computable. Named once, here,
#: so a consumer cannot spell the set differently — the `unverifiable` bucket in the
#: briefing's plan render is the same idea spelled a second time, and it drifted.
UNCOMPUTABLE: frozenset[str] = frozenset({"no_checkboxes", "no_acceptance", "unowned"})

#: The partition's classes in reading order, for a printer that renders every one of
#: them. Wording used to live here as a Russian `CLASS_NOUN` map, which put display
#: prose in the pure core and fixed the language of every surface downstream; the words
#: are now in `status.words` under `proof.specs`, and this module hands over counts.
CLASS_ORDER: tuple[AcceptanceClass, ...] = (
    "measured",
    "no_checkboxes",
    "no_acceptance",
    "unowned",
)


@dataclass(frozen=True)
class SpecAcceptance:
    """One spec's acceptance state, as read — never as rendered.

    `done`/`total` are `None` for every class but `measured`, and that is the point:
    a zero here would be indistinguishable from a spec that lists ten unticked boxes,
    which is model-level rule 6. The type refuses the conflation rather than asking
    each printer to remember it.
    """

    spec_id: str
    title: str
    klass: AcceptanceClass
    owner_field: str | None = None
    provenance: str = ""
    done: int | None = None
    total: int | None = None
    advisor_open: int = 0

    def __post_init__(self) -> None:
        if self.klass == "measured":
            if self.done is None or self.total is None:
                raise ValueError(
                    f"{self.spec_id}: a measured spec carries its counts — "
                    "None here is the absence/zero collapse this class exists to prevent"
                )
            if self.total <= 0:
                raise ValueError(
                    f"{self.spec_id}: total={self.total} is not measured, it is "
                    "'no_checkboxes' — classify, do not count"
                )
            if not 0 <= self.done <= self.total:
                raise ValueError(f"{self.spec_id}: done={self.done} outside 0..{self.total}")
        elif self.done is not None or self.total is not None:
            raise ValueError(
                f"{self.spec_id}: class {self.klass!r} carries no counts; got "
                f"done={self.done}, total={self.total}"
            )

    @property
    def computable(self) -> bool:
        return self.klass == "measured"


def classify(
    *, owner_field: str | None, has_acceptance_block: bool, total: int
) -> AcceptanceClass:
    """The one place a spec's acceptance state is named. Total, and in reading order.

    Every branch is a state the corpus actually holds — none is defensive. `unowned`
    comes first because the ownership filter runs first in every caller, so a spec
    without an ownership field never reaches the acceptance parse; saying anything
    else about it would describe a check that did not happen.
    """
    if owner_field is None:
        return "unowned"
    if not has_acceptance_block:
        return "no_acceptance"
    if total <= 0:
        return "no_checkboxes"
    return "measured"


@dataclass(frozen=True)
class SpecTally:
    """The partition, counted. `total` is every spec seen, not every spec speakable."""

    total: int
    by_class: dict[str, int]
    boxes_done: int
    boxes_total: int

    def __post_init__(self) -> None:
        counted = sum(self.by_class.values())
        if counted != self.total:
            raise ValueError(
                f"the partition lost {self.total - counted} spec(s): {self.by_class} "
                f"sums to {counted}, not {self.total} — a class is missing, and a spec "
                "in no class is exactly the invisibility this module was written for"
            )

    @property
    def measured(self) -> int:
        return self.by_class.get("measured", 0)

    @property
    def uncomputable(self) -> int:
        return sum(n for k, n in self.by_class.items() if k in UNCOMPUTABLE)

    def proof_breakdown(self) -> dict[str, int]:
        """The partition as numbers, for `Count.proof` — every class, zeros included.

        Zeros are present because this is an inventory surface: rule 3 states success
        in words, and "0 without an acceptance block" is the sentence that tells a
        reader the instrument looked and found none, rather than that it did not look.
        A class omitted here cannot be stated by any printer, so the omission would be
        silent on every surface at once.

        Returns counts rather than a finished clause: the clause is one phrase in the
        catalog (`proof.specs`), which is what lets its wording, its separators and its
        order change per language without this module knowing any of them.
        """
        return {k: self.by_class.get(k, 0) for k in CLASS_ORDER}


def tally(rows: Iterable[SpecAcceptance]) -> SpecTally:
    """Count the partition. Sums the checkbox totals of the measured class only."""
    by_class: dict[str, int] = {}
    total = boxes_done = boxes_total = 0
    for row in rows:
        total += 1
        by_class[row.klass] = by_class.get(row.klass, 0) + 1
        if row.klass == "measured":
            assert row.done is not None and row.total is not None  # enforced in __post_init__
            boxes_done += row.done
            boxes_total += row.total
    return SpecTally(
        total=total, by_class=by_class, boxes_done=boxes_done, boxes_total=boxes_total
    )
