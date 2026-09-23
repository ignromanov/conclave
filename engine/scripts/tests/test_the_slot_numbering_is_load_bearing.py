"""A slot is addressed by its number from five documents, so the number is an API (#316).

`output-formatting.md` §Report slots is a numbered table. Four other shipped documents point
into it *by number* — `commands/processing.md` and `commands/start.md` route fields into
"slot 2", `state-report.md` inherits "slot 6", `output-discipline.md` counts rows "inside
slot 3" — and `state-report.md` also hardcodes the table's length as "the 8-slot task-report
skeleton". Twenty-five such references were measured. None carries anything that breaks when
the table changes.

WHY THIS GATE EXISTS AT ALL. #316 asked for "three additions to the Report-slots table". Taken
literally that is a renumbering: a row inserted anywhere above the end silently re-points every
"slot N" reference in five documents at the wrong slot, and a row appended at the end silently
falsifies the hardcoded count. The suggested fix for a contract defect would have introduced a
second, quieter contract defect of exactly the class #315 had just finished closing — a document
asserting something no longer true, with nothing able to fail.

The repair #316 actually needs turned out not to require a renumbering: all three of its findings
are qualifications on **slot 4**, not new slots. But that was a choice, and next time it will be
someone else's. This gate is what makes it a checked one.

WHAT IT PINS, AND WHAT IT DELIBERATELY DOES NOT. Three things a machine can settle: numbering is
contiguous from 1, every reference resolves to a slot that exists, and every reference that a
document *names* as well as numbers agrees with the table. It does not judge whether a reference
points at the slot its argument needs — that is meaning, and a gate guessing at it would be the
"assertions true either way" failure with extra steps.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
CONTRACT = REPO / "skills" / "advisor-contracts" / "references" / "output-formatting.md"

#: A row of the §Report slots table: `| 4 | **evidence** — test output ... | MUST |`.
SLOT_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*\*\*([^*]+)\*\*")

#: "slot 2", "Slot 6", "slots 2 and 3", "slots 1–2", "slot 4/6". The second number is captured
#: so a pair or range is checked at both ends rather than only at the first.
SLOT_REF = re.compile(r"\bslots?\s+(\d+)\s*(?:(?:and|or|[-–/,])\s*(\d+))?", re.IGNORECASE)

#: The table's own length, asserted in prose one document away.
SLOT_COUNT_CLAIM = re.compile(r"\b(\d+)-slot\b")

#: A slot name counts as *named* only when it is set off as one — backticked, bolded, or
#: written as a hyphenated compound (`not-checked`). Bare words in running prose do not count:
#: `changed`, `evidence` and `where` are ordinary vocabulary, and reading them as slot names
#: would manufacture disagreements the text never claims.
#: The newline in the first character class is load-bearing: `commands/processing.md` wraps
#: ``slot 2 (`required /`` and closes the backtick on the next line, and without it that
#: document — one of the five that point into the table — is silently never judged.
MARKED_NAME = re.compile(r"[`*]([A-Za-z][A-Za-z /_\n-]{2,30})[`*]|\b([a-z]+-[a-z]+)\b")

#: How far a name may sit from a reference and still be read as naming it.
REACH = 120

#: Surfaces that may point into the table. Everything a session actually loads.
SURFACES = ("commands/*.md", "skills/*/SKILL.md", "skills/*/references/*.md")


def _slots() -> dict[int, str]:
    """The numbered table, read from the contract rather than restated here."""
    out: dict[int, str] = {}
    inside = False
    for line in CONTRACT.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Report slots"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside and (match := SLOT_ROW.match(line)):
            out[int(match.group(1))] = match.group(2).strip()
    return out


def _documents() -> dict[str, str]:
    docs: dict[str, str] = {}
    for pattern in SURFACES:
        for path in sorted(REPO.glob(pattern)):
            docs[str(path.relative_to(REPO))] = path.read_text(encoding="utf-8")
    return docs


def _normalise(name: str) -> str:
    """`not checked`, `not-checked` and `Not Checked` are one name; so are the `/` forms."""
    return re.sub(r"[\s/_-]+", " ", name).strip().lower()


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _references() -> list[tuple[str, int, int]]:
    """Every `slot N` in the shipped surfaces, as (document, line, number)."""
    found: list[tuple[str, int, int]] = []
    for name, text in _documents().items():
        for match in SLOT_REF.finditer(text):
            line = _line_of(text, match.start())
            found.extend(
                (name, line, int(match.group(g))) for g in (1, 2) if match.group(g)
            )
    return found


def _name_claims() -> list[tuple[str, int, int, int]]:
    """Pairs a document asserts, as (document, line, number written, slot the name means).

    NEAREST REFERENCE, NOT A WINDOW. A first cut scored a fixed window around each reference
    and produced two findings it could not support: at `commands/start.md:413` the window
    reached back over a line break to slot 2's trailing parenthetical and read it as slot 5's
    name, and at `output-formatting.md:274` it reached up into the table and read slot 8's
    *defining* row as a claim about slot 6. Both false, both green-looking, and both the #316
    failure itself — a claim checked by an instrument that could not have said otherwise.

    A window is a proximity proxy, not a containment test, and names attach on either side
    (``slot 2 (`required / assumed`)`` trails; `**not checked** (… slot 6)` leads). So each
    *name* is assigned to the single nearest reference instead, and table rows are excluded
    because a row defines a slot rather than pointing at one.
    """
    by_name = {_normalise(name): number for number, name in _slots().items()}
    claims: list[tuple[str, int, int, int]] = []
    for document, text in _documents().items():
        #: Only the rows that *define* a slot are excluded, not every table row. Excluding
        #: all of them dropped `state-report.md`'s contract-comparison table, which cites
        #: "slot 6 not-checked" inside a cell and is a pointer like any other.
        rows = {
            _line_of(text, m.start())
            for m in re.finditer(r"^\s*\|\s*\d+\s*\|\s*\*\*[^*]+\*\*", text, re.MULTILINE)
        }
        refs = [
            (m.start(), m.end(), int(m.group(1)))
            for m in SLOT_REF.finditer(text)
            if _line_of(text, m.start()) not in rows
        ]
        if not refs:
            continue
        for match in MARKED_NAME.finditer(text):
            meant = by_name.get(_normalise(match.group(1) or match.group(2)))
            if meant is None or _line_of(text, match.start()) in rows:
                continue
            gap, written = min(
                (max(start - match.end(), match.start() - end, 0), number)
                for start, end, number in refs
            )
            if gap <= REACH:
                claims.append((document, _line_of(text, match.start()), written, meant))
    return claims


# ----------------------------------------------------------------------------- the gate


def test_the_slot_numbers_are_contiguous_from_one() -> None:
    slots = _slots()
    assert slots, "the §Report slots table did not parse — the gate has no subject"
    assert sorted(slots) == list(range(1, len(slots) + 1)), (
        f"slot numbering is not 1..{len(slots)}: {sorted(slots)}"
    )


def test_every_slot_reference_resolves_to_a_slot_that_exists() -> None:
    slots = _slots()
    dangling = [
        f"  {where}:{line}: slot {number} (the table has 1..{len(slots)})"
        for where, line, number in _references()
        if number not in slots
    ]
    assert not dangling, "a document points at a slot that is not there:\n" + "\n".join(dangling)


def test_a_reference_that_names_a_slot_agrees_with_the_table() -> None:
    """The one with teeth: a renumbering breaks the name/number pair and nothing else."""
    slots = _slots()
    wrong = [
        f"  {where}:{line}: written as slot {written}, but names slot {meant} "
        f"({slots[meant]!r})"
        for where, line, written, meant in _name_claims()
        if written != meant
    ]
    assert not wrong, (
        "a slot reference names one slot and numbers another:\n" + "\n".join(wrong)
    )


def test_the_hardcoded_slot_count_matches_the_table() -> None:
    expected = len(_slots())
    wrong = [
        f"  {where}:{n}: claims a {match.group(1)}-slot skeleton; the table has {expected}"
        for where, text in _documents().items()
        for n, line in enumerate(text.splitlines(), 1)
        for match in SLOT_COUNT_CLAIM.finditer(line)
        if int(match.group(1)) != expected
    ]
    assert not wrong, "a document states the table's length and is wrong:\n" + "\n".join(wrong)


# -------------------------------------------------------- the instrument, held to its job


def test_the_scan_reaches_the_documents_that_point_into_the_table() -> None:
    """Anti-vacuity. Every assertion above passes trivially on an empty reference set."""
    refs = _references()
    assert len(refs) >= 20, f"only {len(refs)} slot references found; 25 were measured"
    sources = {where for where, _, _ in refs}
    for expected in (
        "commands/processing.md",
        "commands/start.md",
        "skills/advisor-contracts/references/state-report.md",
        "skills/advisor-contracts/references/output-discipline.md",
        "skills/advisor-contracts/references/output-formatting.md",
    ):
        assert expected in sources, f"{expected} points into the table and the scan missed it"


def test_the_name_check_has_live_subjects_and_they_all_agree() -> None:
    """The check above is satisfied by finding nothing. This says it finds something.

    Four pairs across three documents were measured. If a rewording drops that to zero the
    check silently stops guarding, which is the exact shape of the defect #315 closed — a rule
    that reads as enforced and enforces nothing. Both of the ways this number was lost during
    development were real and quiet: excluding every table row rather than only slot-defining
    ones, and a name hard-wrapped across a line break.
    """
    claims = _name_claims()
    assert len(claims) >= 4, f"only {len(claims)} name/number pairs found; 4 were measured"
    assert {where for where, _, _, _ in claims} >= {
        "commands/processing.md",
        "commands/start.md",
        "skills/advisor-contracts/references/state-report.md",
    }


def test_the_count_check_has_a_subject() -> None:
    """The count check is the *only* thing that sees a slot appended at the end.

    Mutation measured it: a row added after the last one keeps the numbering contiguous and
    breaks no existing pointer, so `test_the_hardcoded_slot_count_matches_the_table` is the
    single assertion that fires — and it has exactly one subject in the whole distribution,
    the phrase "the 8-slot task-report skeleton" in `state-report.md`. Reword that sentence and
    an appended slot becomes invisible to everything, with no test going red to say so.
    """
    subjects = [
        f"{where}:{n}"
        for where, text in _documents().items()
        for n, line in enumerate(text.splitlines(), 1)
        if SLOT_COUNT_CLAIM.search(line)
    ]
    assert subjects, (
        "no document states the table's length any more, so appending a slot is now "
        "unguarded; either restore the claim or give the table a different anchor"
    )


def test_the_matcher_reads_the_shapes_the_documents_actually_use() -> None:
    """Each line here was copied from a live one; the pair forms are why group 2 exists."""

    def numbers(text: str) -> list[int]:
        return [int(g) for m in SLOT_REF.finditer(text) for g in m.groups() if g]

    assert numbers("report it in the run's terminal block as slot 2 (`required /") == [2]
    assert numbers("If a length budget bites, it bites slots 2 and 3.") == [2, 3]
    assert numbers("Past the budget, slots 1–2 lead and slot 4/6 detail moves") == [1, 2, 4, 6]
    assert numbers("- **not checked** (output-formatting slot 6) transfers") == [6]
    assert numbers("a slotted screwdriver and 8 slots of memory") == []
    count = SLOT_COUNT_CLAIM.search("the 8-slot task-report skeleton")
    assert count is not None and count.group(1) == "8"
