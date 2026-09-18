"""Every `mechanical` principle names a check that has been seen red — by running it red.

`constitution.md` §6 makes this a precondition of the tier, in its own words: *"A check never
seen red is a check never seen."* Until now the charter required that observation and nothing
made it, so `mechanical` meant "a test with this name exists on disk".

The gap is not academic. `test_constitution.py` verifies that principle I's check resolves to a
`def` in a file; it cannot notice that the same test would pass with the archive path throwing
away half of every review. That is the distinction this suite has spent its history on — a check
that runs is not yet a check that covers (#110), a meta-test can pass while the real defect
passes with it (spec 116) — applied to the document that governs the rest.

Cost: one copy of the tracked tree, then one pytest process per falsification. It is the most
expensive gate in the suite and the only one that grades the governing document, so it is not
marked optional. If that ever stops being an acceptable trade, the honest move is to mark it and
say so here, not to weaken what it asserts.
"""
from __future__ import annotations

import re

import pytest

from tests.charter_falsification import (
    FALSIFICATIONS,
    REPO_ROOT,
    apply,
    run_check,
    working_tree_copy,
)

CHARTER = REPO_ROOT / "constitution.md"

_PRINCIPLE_RE = re.compile(r"^### (0|[IVX]+)\. (.+)$")
_TIER_RE = re.compile(r"^\*\*Tier\*\*: `(\w+)`")
_CHECK_RE = re.compile(r"\*\*Check\*\*: `([^`]+)`")
_FALSIFIED_RE = re.compile(r"\*\*Falsified by\*\*: `([^`]+)`")


def _mechanical() -> dict[str, tuple[str, str | None]]:
    """numeral -> (check, falsification id) for every principle tagged `mechanical`."""
    out: dict[str, tuple[str, str | None]] = {}
    current: str | None = None
    body: list[str] = []

    def flush() -> None:
        if current is None:
            return
        text = "\n".join(body)
        tier = next((m.group(1) for m in map(_TIER_RE.match, body) if m), None)
        if tier != "mechanical":
            return
        check = _CHECK_RE.search(text)
        fals = _FALSIFIED_RE.search(text)
        out[current] = (check.group(1) if check else "", fals.group(1) if fals else None)

    for line in CHARTER.read_text(encoding="utf-8").splitlines():
        m = _PRINCIPLE_RE.match(line)
        if m:
            flush()
            current, body = m.group(1), []
            continue
        if line.startswith(("## ", "### ")):
            flush()
            current, body = None, []
            continue
        if current:
            body.append(line)
    flush()
    return out


def test_the_charter_still_has_mechanical_principles():
    """A gate that grades zero principles passes over any charter at all.

    The same guard the rest of this suite applies to its own perimeter: if the heading or tier
    format changes, `_mechanical()` returns {} and every assertion below becomes vacuously true
    — green, and about nothing.
    """
    found = _mechanical()
    assert found, (
        "no principle parsed as `mechanical` — the charter's heading or **Tier** format changed, "
        "and this gate is now grading an empty set"
    )


def test_every_mechanical_principle_names_a_registered_falsification():
    """The declaration half — cheap, and it fails before the expensive half wastes a copy."""
    problems = []
    for numeral, (check, fals) in sorted(_mechanical().items()):
        if not check:
            problems.append(f"principle {numeral}: mechanical, names no **Check**")
        if fals is None:
            problems.append(
                f"principle {numeral}: mechanical, names no **Falsified by** — §6 requires its "
                "check to have been observed failing on a violation"
            )
        elif fals not in FALSIFICATIONS:
            problems.append(f"principle {numeral}: **Falsified by** `{fals}` is not registered")
    assert not problems, "charter falsification claims are not honest:\n  " + "\n  ".join(problems)


def test_no_falsification_is_registered_for_a_principle_that_does_not_claim_it():
    """The registry may not drift ahead of the document it serves.

    An entry whose principle is no longer `mechanical` — downgraded, renumbered, deleted — would
    otherwise sit here being exercised, and a passing run would suggest a tier that the charter
    has stopped claiming.
    """
    mechanical = _mechanical()
    orphans = {
        fid: f.principle for fid, f in FALSIFICATIONS.items()
        if f.principle not in mechanical or mechanical[f.principle][1] != fid
    }
    assert not orphans, f"registered falsifications no principle claims: {orphans}"


@pytest.mark.parametrize("fid", sorted(FALSIFICATIONS))
def test_the_named_check_passes_clean_and_fails_on_the_violation(fid, tmp_path):
    """Green first, then red. Either half alone certifies nothing.

    Red-only would be satisfied by a check that is broken and fails on everything; green-only is
    what the charter already had. The pair is the observation §6 asks for, and it is re-made on
    every run rather than recorded once and trusted — a claim that was true when written is the
    cache this project keeps finding stale.
    """
    f = FALSIFICATIONS[fid]
    check = _mechanical()[f.principle][0]

    tree = working_tree_copy(tmp_path / "tree")

    clean_ok, clean_out = run_check(tree, check)
    assert clean_ok, (
        f"{fid}: the check named by principle {f.principle} does not pass on an unmutated tree, "
        f"so its failure below would prove nothing about the mutation.\n{clean_out}"
    )

    apply(tree, f)

    mutated_ok, mutated_out = run_check(tree, check)
    assert not mutated_ok, (
        f"{fid}: {check} SURVIVED the violation it is named for.\n"
        f"The mutation: {f.destroys}\n"
        f"Principle {f.principle} is tagged `mechanical` on a check that does not catch this.\n"
        f"{mutated_out}"
    )
