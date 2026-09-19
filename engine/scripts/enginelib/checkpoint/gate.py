"""gate.py — the close gate: a completion is re-checked before the count is published (117 T8).

R12. `shipped M` is written into the session record as a statement about the present tense, and
the checks that justified it ran at append time — possibly days earlier. A commit can be rebased
out from under the line that cites it, an artefact can be deleted, a predicate can regress. The
row would still say M, and would still read as the one number in the record that rests on
something external.

So every completed unit is resolved again here, and a unit whose evidence no longer holds is a
**disagreement**: the record claims a completion the world does not currently show.

**The refusal is escapable and the escape does not silence** — that half is the ruling's, not the
implementer's. A gate that can only be obeyed is a wall met at the end of a session whose work is
already done; a warning goes to scrollback and dies. Forcing the close writes the disagreement into
the record, where it outlives the session and can be counted. The kill criterion reads off exactly
those lines: over the first 10 closes where the gate fires, three overrides showing the gate was
wrong demote it to the written line alone.

**A check that could not be run is not a disagreement.** This is the distinction `Check.unknown`
exists for and it is the difference between a gate and a nuisance: a gh snapshot goes stale in 900
seconds and every session outlives that, so reading a stale cache as a vanished issue would refuse
every close carrying `issue:` evidence — a refusal keyed on the evidence class rather than on
anything that happened. Silence about what could not be observed is the honest report.

No stdout, no argparse, no sys.exit — the adapter decides what a refusal looks like. Resolution
executes git and the filesystem, which is the point of it.
"""
from __future__ import annotations

from dataclasses import dataclass

from enginelib.checkpoint import evidence, record


@dataclass(frozen=True)
class Disagreement:
    """One completed unit, and the one ref of it that no longer resolves.

    A unit with two failing refs yields two of these. They are not collapsed: the gap the operator
    has to judge is per-artefact — one missing file and one rebased-away commit are different
    questions with different answers, and a joined line makes the reader open the record to find
    out which.
    """

    unit: str
    ref: str
    reason: str


def disagreements(
    entries: tuple[record.Entry, ...] | list[record.Entry],
    roots: evidence.Roots,
) -> tuple[Disagreement, ...]:
    """Completed units whose evidence no longer holds, in the order the record names them.

    Intents are not examined and their absence from this list is not an oversight: a declared unit
    that never completed is already `lost` in R5's row, and it is a normal end to a session. R12 is
    about the opposite failure — a *claimed completion* that nothing currently confirms.
    """
    found: list[Disagreement] = []
    for entry in entries:
        if entry.kind != record.KIND_DONE:
            continue
        for check in evidence.resolve_all(entry.evidence, roots):
            if check.ok or check.unknown:
                continue
            found.append(Disagreement(entry.text, check.ref, check.reason))
    return tuple(found)


def render(found: tuple[Disagreement, ...] | list[Disagreement]) -> str:
    """The gap, named. One line per disagreement, quoting the unit as the record holds it.

    The same text serves the refusal the operator reads in the terminal and the durable line an
    override writes into the record, and that is deliberate: two wordings of one fact drift, and
    the operator who overrode would then be unable to find, in the record, the sentence they
    decided against.
    """
    return "\n".join(f"- {d.unit} — {d.ref}: {d.reason}" for d in found)
