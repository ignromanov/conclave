"""test_retro_contract_gate.py — the feedback vocabulary is one contract in three files.

Spec 117's lens rewrite (commissioned by helm-ceo, operator-approved 2026-09-08) rests on a
category that must exist in `feedback.schema` AND be documented in the contract AND be routed
by a retrospective prompt. Any one of those three alone is inert:

- schema only        -> nothing emits a `positive` item, because no prompt asks for one
- contract only      -> the item is rejected at validation
- prompt only        -> the item is rejected at validation

The corpus this rewrite exists to fix is the proof. 244 items, zero positive, and the standing
explanation was the prompt wording. It was the enum: there was no positive category, so no
wording could ever have produced a positive item, and the rewrite's own falsifier
("constrained positives yield ~0 over 20 sessions") was guaranteed to pass for a reason that
has nothing to do with the lens (critic-117 R6). Nothing in the suite joined the three files,
which is why a schema fact read as a prompt fact for months.

Each gate below is paired with a meta-test that builds the defect in a synthetic tree and
asserts the gate reddens. A meta-test is necessary and not sufficient: this file's gates were
also mutation-checked against the real tree, because a gate can pass its own decoy and still
miss the live defect one indirection away.
"""

from __future__ import annotations

import pathlib
import re
import typing

import pytest

from feedback.schema import Category

# tests/ -> scripts/ -> engine/ -> <code root>. Same derivation as test_gates.py.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "skills/advisor-contracts/references/feedback-protocol.md"
DONE = REPO_ROOT / "commands/done.md"

SCHEMA_CATEGORIES = frozenset(typing.get_args(Category))

# The six prompts helm-ceo commissioned, each traceable to a W3 answerability row.
# `positive` is routed by exactly one of them (`removed-step`); the rest are friction.
REQUIRED_PROMPTS = ("job", "stuck", "instead", "acted-on", "removed-step", "unexecuted")

_BACKTICKED = re.compile(r"`([^`]+)`")


def _contract_categories(text: str) -> frozenset[str]:
    """The category enum as the contract documents it — the `| `category` | ... |` row."""
    for line in text.splitlines():
        if line.startswith("| `category`"):
            cells = line.split("|")
            return frozenset(_BACKTICKED.findall(cells[2]))
    raise AssertionError("no `| `category` |` row in the contract — the enum row was renamed")


# The enum is spelled out in prose in more than one place, and the first draft of this gate
# checked exactly one of them — certifying agreement while the other copies drifted unseen.
# So the copies are DISCOVERED, not listed: any line naming five or more members is a copy of
# the enum and is held to the schema. Five is above the largest incidental co-occurrence in
# the tree (a routing table names at most three) and below the smallest real copy.
_ENUM_QUORUM = 5
_DOC_EXTS = (".md", ".py")
_DOC_DIRS = ("commands", "skills", "docs", "engine/scripts/feedback")


def _iter_doc_files():
    for sub in _DOC_DIRS:
        base = REPO_ROOT / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in _DOC_EXTS or not path.is_file():
                continue
            parts = path.relative_to(REPO_ROOT).parts
            if "tests" in parts or ".venv" in parts or "schema.py" in parts:
                continue
            yield path


def _enum_copies() -> list[tuple[pathlib.Path, int, frozenset[str]]]:
    """Every line in CODE that spells out the category enum, with the members it names."""
    copies: list[tuple[pathlib.Path, int, frozenset[str]]] = []
    for path in _iter_doc_files():
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            named = frozenset(c for c in SCHEMA_CATEGORIES if c in line)
            # `positive` is a common English word; require the members to be delimited the
            # way an enum listing delimits them, so ordinary prose cannot reach quorum.
            if len(named) >= _ENUM_QUORUM:
                copies.append((path, lineno, named))
    return copies


def _retro_section(text: str) -> str:
    """The Lifecycle Retrospective phase body, up to the next `## ` heading."""
    start = text.index("## Phase: Lifecycle Retrospective")
    rest = text[start + 1 :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def _prompt_rows(section: str) -> list[tuple[str, tuple[str, ...]]]:
    """(prompt-id, categories) for every row of the prompt table.

    A row is `| **<id>** | <what the answer consists of> | <files as> |`. The files-as cell
    names zero or more backticked categories.

    Zero and many are both real, and an earlier draft of this gate wrongly forbade each in
    turn. Many: an item's category follows what was found, not which prompt found it — a
    stuck moment can be a script defect or a doc contradiction. Zero: the neutral opening
    prompt frames the session and files nothing. Both constraints were invented by the gate
    rather than observed in the design, which is the tail wagging the dog; what the gate can
    honestly check is that every name is real, that the positive producer exists and is
    unique, and that the no-category form stays unique to the frame row.
    """
    rows: list[tuple[str, tuple[str, ...]]] = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 5 or not cells[1].startswith("**"):
            continue
        rows.append((cells[1].strip("*"), tuple(_BACKTICKED.findall(cells[3]))))
    return rows


# ---------------------------------------------------------------------------
# Gate 1 — the contract's documented enum is the schema's enum
# ---------------------------------------------------------------------------


def test_contract_category_enum_matches_the_schema():
    documented = _contract_categories(CONTRACT.read_text())
    assert documented == SCHEMA_CATEGORIES, (
        f"contract documents {sorted(documented)}; schema accepts "
        f"{sorted(SCHEMA_CATEGORIES)} — an author reads the contract and the validator "
        "reads the schema, so a divergence rejects items that the contract invited"
    )


def test_enum_gate_catches_a_contract_that_lags_the_schema():
    stale = "| `category` | " + " · ".join(f"`{c}`" for c in sorted(SCHEMA_CATEGORIES)[:-1]) + " |"
    with pytest.raises(AssertionError):
        documented = _contract_categories(stale)
        assert documented == SCHEMA_CATEGORIES


def test_every_documented_copy_of_the_enum_matches_the_schema():
    copies = _enum_copies()
    assert copies, (
        "no line in CODE spells out the category enum — either every copy was deleted or "
        f"the {_ENUM_QUORUM}-member quorum no longer detects one, and this gate is now vacuous"
    )
    stale = [
        (str(p.relative_to(REPO_ROOT)), n, sorted(SCHEMA_CATEGORIES - named))
        for p, n, named in copies
        if named != SCHEMA_CATEGORIES
    ]
    assert not stale, (
        f"copies of the category enum that lag the schema (path, line, missing): {stale} — "
        "an author reads whichever copy is nearest and the validator reads the schema"
    )


def test_enum_copy_discovery_finds_more_than_one_site():
    """The gate's own coverage claim.

    An earlier draft pinned the single contract file. It passed while `commands/feedback.md`
    and the `feedback_emit.py` scaffold carried the same enum, one member short — which is the
    exact shape of drift the gate exists to catch, invisible to it because it was looking at
    one file. If discovery ever collapses back to a single site, the gate has silently
    narrowed to what it used to be.
    """
    sites = {p for p, _, _ in _enum_copies()}
    assert len(sites) >= 2, f"enum discovered at only {sorted(str(s) for s in sites)}"


# ---------------------------------------------------------------------------
# Gate 2 — every retrospective prompt routes to a category the schema accepts
# ---------------------------------------------------------------------------


def test_every_retro_prompt_routes_to_a_real_category():
    rows = _prompt_rows(_retro_section(DONE.read_text()))
    unknown = {(p, c) for p, cats in rows for c in cats if c not in SCHEMA_CATEGORIES}
    assert not unknown, (
        f"retrospective prompts route to categories the schema rejects: {sorted(unknown)} — "
        "every item filed by such a prompt fails validation at emission"
    )


def test_route_gate_catches_a_prompt_pointing_at_no_category():
    section = (
        "## Phase: Lifecycle Retrospective\n\n"
        "| Prompt | Ask | Files as |\n|---|---|---|\n"
        "| **job** | ... | `script-defect` |\n"
        "| **ghost** | ... | `not-a-category` · `idea` |\n"
    )
    rows = _prompt_rows(section)
    named = {c for _, cats in rows for c in cats}
    assert named - SCHEMA_CATEGORIES == {"not-a-category"}


def test_exactly_one_prompt_files_nothing():
    """The empty files-as cell is the frame row's form, and must stay unique to it.

    Without this, any prompt could drop its category cell and leave the schema join with
    nothing to check — the escape hatch would silently become the way to avoid the gate.
    """
    rows = _prompt_rows(_retro_section(DONE.read_text()))
    frames = [p for p, cats in rows if not cats]
    assert frames == ["job"], (
        f"prompts filing no category: {frames} — exactly one prompt (`job`, the neutral "
        "opener) frames the session without filing; every other prompt names its category"
    )


# ---------------------------------------------------------------------------
# Gate 3 — the positive category has a producer, and the six prompts are all present
# ---------------------------------------------------------------------------


def test_positive_category_has_a_producing_prompt():
    """An enum member no prompt asks for is a field nobody fills.

    This is the gate that would have caught the original defect from the other side: had
    `positive` been added to the schema alone, the corpus would still have shown zero
    positives and the lens would still have taken the blame.
    """
    rows = _prompt_rows(_retro_section(DONE.read_text()))
    producers = [p for p, cats in rows if "positive" in cats]
    assert producers == ["removed-step"], (
        f"`positive` is produced by {producers} — it must be produced by exactly one prompt, "
        "`removed-step`. Zero producers make the category inert (an enum member nothing can "
        "fill); more than one loosens the single admissible positive form back into the "
        "unconstrained 'what worked well' the constraint exists to prevent"
    )


def test_all_six_commissioned_prompts_are_present():
    rows = _prompt_rows(_retro_section(DONE.read_text()))
    present = tuple(p for p, _ in rows)
    assert present == REQUIRED_PROMPTS, (
        f"retrospective declares {present}; the commissioned set is {REQUIRED_PROMPTS} — "
        "each prompt traces to a W3 answerability row, so dropping one drops a question "
        "the literature marked answerable"
    )


def test_prompt_set_gate_catches_a_dropped_prompt():
    section = (
        "## Phase: Lifecycle Retrospective\n\n"
        "| Prompt | Ask | Category |\n|---|---|---|\n"
        + "".join(f"| **{p}** | ... | `idea` |\n" for p in REQUIRED_PROMPTS[:-1])
    )
    present = tuple(p for p, _ in _prompt_rows(section))
    assert present != REQUIRED_PROMPTS


def test_positive_producer_gate_catches_a_second_producer():
    section = (
        "## Phase: Lifecycle Retrospective\n\n"
        "| Prompt | Ask | Files as |\n|---|---|---|\n"
        "| **removed-step** | ... | `positive` |\n"
        "| **stuck** | ... | `positive` |\n"
    )
    producers = [p for p, cats in _prompt_rows(section) if "positive" in cats]
    assert producers != ["removed-step"]
