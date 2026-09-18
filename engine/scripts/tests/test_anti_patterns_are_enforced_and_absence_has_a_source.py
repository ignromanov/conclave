"""Every shipped anti-pattern names its enforcer, and absence names its instrument (#104).

#104 asks whether the command proxy's loss is a filter, a truncation or a cache.
Measured on this harness it is none of the three — it is **substitution**. A PreToolUse
hook hands the command to a rewriter, and a different program runs:

    written:  head -5 README.md      ran: rtk read README.md --max-lines 5
    written:  git diff > patch.file  ran: rtk git diff > patch.file

The second one is the dangerous shape, and it reproduces deterministically: the file
lands at 140 bytes of human-readable summary, `git apply --check` answers "No valid
patches in input", and every check anyone would actually run — the command exited 0, the
file exists, it is not empty — passes. #104 reports exactly this costing eight files of
another session's uncommitted work.

The rule that follows ("anything load-bearing runs unproxied; an absence claim states
which instrument produced it") was, until this file, stated on NO shipped surface. It
lived in one advisor's private memory and in scattered DATA working docs, so every
session that did not happen to read them asserted absence from a rewritten command with
nothing to warn it. `advisor-anti-patterns.md` is loaded by `commands/start.md` on every
start, which is the only place a rule of this kind can do any work.

The enforcement assertion below is DERIVED, and writing it caught its own first version:
a naive scan for digits read "items 1-3" as {1, 3} and reported item 2 unenforced. An
instrument that cannot read the document's own notation reports the document as broken.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CONTRACT = REPO / "skills" / "advisor-contracts" / "references" / "advisor-anti-patterns.md"

ROW = re.compile(r"^\|\s*(\d+)\s*\|", re.M)
#: `4`, `1-3`, `1–3` — the enforcement section writes both single items and ranges.
ITEM_REF = re.compile(r"(\d+)\s*[-–]\s*(\d+)|(\d+)")


def _text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _rows() -> set[int]:
    return {int(n) for n in ROW.findall(_text())}


def _enforced() -> set[int]:
    """Item numbers the Enforcement section accounts for, ranges expanded."""
    body = _text().split("## Enforcement", 1)[1]
    body = body.split("\n## ", 1)[0]          # stop at the next heading
    out: set[int] = set()
    for lo, hi, single in ITEM_REF.findall(body):
        if single:
            out.add(int(single))
        else:
            out.update(range(int(lo), int(hi) + 1))
    return out


def test_the_scan_reads_the_contract():
    """Anti-vacuity. Two empty sets are a subset of each other, and a regex that matched
    no table row would report perfect enforcement of nothing."""
    rows = _rows()
    assert len(rows) >= 8, f"the row scan read {rows} — it is not reading the table"
    assert _enforced(), "the enforcement scan read nothing"


def test_every_anti_pattern_names_an_enforcer():
    """A rule nobody enforces is a rule the next reader is free to regard as advice."""
    orphans = sorted(_rows() - _enforced())
    assert not orphans, (
        f"anti-pattern(s) {orphans} appear in the table and in no line of the "
        "Enforcement section. Say what catches it — a done-step, an audit, or the "
        "advisor re-running the check — or do not ship it as required."
    )


def test_the_contract_names_an_unproxied_instrument():
    """The rule has to be actionable at the moment it is read. 'Be careful with greps'
    is not: the command that was rewritten looked exactly like one that was not."""
    text = _text()
    for needle in ("/usr/bin/grep", "/usr/bin/git"):
        assert needle in text, (
            f"{CONTRACT.name} does not name {needle}. An advisor told that a command "
            "may have been rewritten, and not told what to run instead, has been given "
            "a worry rather than a procedure (#104)."
        )


def test_the_contract_states_the_mechanism_not_just_the_symptom():
    """'The proxy loses results' invites narrower greps, which #104 measured as no fix —
    the losing `git diff` was already scoped to one branch and one pathspec. Only the
    substitution mechanism explains why a NARROWER command loses just as much, and why
    the output can be confidently wrong rather than merely short."""
    text = _text()
    assert "substitution" in text.lower(), (
        "the contract describes the symptom without the mechanism; a reader will "
        "conclude that scoping the command more tightly fixes it, and #104 measured "
        "that it does not"
    )
    assert "git apply" in text, (
        "the contract does not carry the case where the substitute's output is WRITTEN "
        "somewhere and read back later — the one that destroyed work rather than hiding "
        "it (#104)"
    )
