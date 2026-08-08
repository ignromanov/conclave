"""The placebo is the whole experiment's interpretability. It gets tested like a load-bearing part."""
from __future__ import annotations

import pathlib
import re

import pytest

from evals.arms import (
    ARMS,
    PLACEBO_PATH,
    approx_tokens,
    bcp14_count,
    length_match_error,
    system_prompt,
)
from evals.fixture import NORM_PATTERNS

REPO = pathlib.Path(__file__).resolve().parents[4]
CHARTER = REPO / "constitution.md"

# The charter's own subject matter. A placebo that mentions any of it is not a control.
CHARTER_LEXICON = (
    "record", "delete", "deletion", "archive", "irreversible", "provenance",
    "constitution", "charter", "principle", "spec", "advisor", "lifecycle",
)


def test_absent_arm_appends_nothing():
    assert system_prompt("absent", CHARTER) == ""


def test_full_arm_is_the_charter_verbatim():
    assert system_prompt("full", CHARTER) == CHARTER.read_text(encoding="utf-8")


def test_placebo_is_length_matched_within_2_percent():
    """Equal tokens, equal structural position — that is what 'controls for length' means."""
    assert length_match_error(CHARTER) <= 0.02, (
        f"placebo is {length_match_error(CHARTER):.1%} off the charter's length; "
        f"charter={approx_tokens(CHARTER.read_text())} words, "
        f"placebo={approx_tokens(PLACEBO_PATH.read_text())} words"
    )


def test_placebo_carries_no_charter_content():
    text = PLACEBO_PATH.read_text(encoding="utf-8").lower()
    leaks = [w for w in CHARTER_LEXICON if w in text]
    assert not leaks, f"placebo restates the content it is supposed to control for: {leaks}"


def test_placebo_matches_no_norm_patterns():
    """The real constraint: placebo must not match normalised regexes from fixture.NORM_PATTERNS.

    This test guards against the fixture detecting charter reststatement in the placebo via
    the same regex engine used to strip charter-bearing files from the trial fixture.
    """
    placebo_text = PLACEBO_PATH.read_text(encoding="utf-8")
    norm_re = re.compile("|".join(NORM_PATTERNS), re.IGNORECASE)
    matches = norm_re.findall(placebo_text)
    assert not matches, (
        f"placebo matches real NORM_PATTERNS and would be stripped from fixture: {matches[:5]}"
    )


def test_placebo_matches_the_charter_normative_register():
    """Domain-null, not authority-null. The control holds 'a long document telling you what you
    MUST do' constant; only the subject changes."""
    charter_kw = bcp14_count(CHARTER.read_text(encoding="utf-8"))
    placebo_kw = bcp14_count(PLACEBO_PATH.read_text(encoding="utf-8"))
    assert placebo_kw >= 0.5 * charter_kw, (
        f"placebo has {placebo_kw} BCP-14 keywords vs the charter's {charter_kw} — "
        "too weak a register to control for authority"
    )


def test_unknown_arm_is_an_error():
    with pytest.raises(ValueError, match="unknown arm"):
        system_prompt("half", CHARTER)


def test_arms_are_exactly_three():
    assert ARMS == ("full", "placebo", "absent")
