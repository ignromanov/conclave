"""A minted persona's identity card holds values, not authoring tokens (#118).

`engine advisor create` renders `personality-template.md` through a `str.replace`
chain that was **lowercase-only** — `{{name}} {{emoji}} {{role}}`. The template's
identity card is written in title case, so every one of its rows survived scaffolding
verbatim, and the first briefing a new consumer ever opened read:

    | **Name** | {{Name}} |

The template's own closing line claimed a gate existed — "Empty placeholders fail the
post-scaffold lint" — and no such lint was ever written. That is the whole mechanism:
a contract asserted in prose, enforced nowhere, false from the day it was written.

## Why this file, and not one more assert in test_advisor_create.py

Two gates, and they pull in OPPOSITE directions. That opposition is the point:

- `test_identity_card_carries_no_unfilled_token` says the card must be resolved.
- `test_the_authoring_prompts_survive_scaffolding` says the prose prompts must NOT be.

A fix that satisfies only the first is one line away and has already shipped once in
this repo: `register.create_executor` collapses leftovers with
`re.sub(r"\\{\\{[^}]*\\}\\}", "TBD by self-introduction", ...)`. Applied here it would
green the first gate while erasing the 4-axis voice well that `hire.md` §3a.5 greps to
validate a hire — which is exactly the defect #75 was filed and fixed for. Whoever
reaches for that one-liner must be stopped by a red test, not by having read #75.

## Derived, not enumerated

The card's rows are read out of the TEMPLATE, never listed here. A row added to the
template that `create()` does not learn to fill turns this red by itself. A hand-kept
list of the five fields would be the same defect one layer up — the lowercase replace
chain WAS a hand-kept list, and it went stale the moment the card was written.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.cmd.helpers import run_engine

#: `{{Anything}}`, greedy-free so it cannot span two tokens on one line.
TOKEN = re.compile(r"\{\{[^{}]*\}\}")

#: A row of the identity-card table: `| **Field** | value |`.
CARD_ROW = re.compile(r"^\|\s*\*\*(?P<field>[^*]+)\*\*\s*\|(?P<value>[^|]*)\|\s*$")

ADVISOR = "vera-cto"
EMOJI = "🛰️"
COLOR = "cyan"
ROLE = "QA"


@pytest.fixture
def minted(tmp_path) -> str:
    """The persona `engine advisor create` actually writes. Run for real.

    Rendering the template in-process would test a copy of the replace chain rather
    than the shipped path — and the shipped path is where the tokens were missed.
    """
    r = run_engine(
        "advisor", "create",
        "--id", ADVISOR, "--role", ROLE, "--color", COLOR, "--emoji", EMOJI,
        env={"CONCLAVE_AI_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0, r.stderr
    persona = (
        tmp_path / ".claude" / "skills" / f"conclave-{ADVISOR}"
        / "memory" / "personality.md"
    )
    assert persona.is_file(), (
        f"no persona at {persona} — create() moved it, and every assertion below "
        "would be measuring a file that does not exist"
    )
    return persona.read_text(encoding="utf-8")


def _card_rows(text: str) -> dict[str, str]:
    return {
        m.group("field").strip(): m.group("value").strip()
        for line in text.splitlines()
        if (m := CARD_ROW.match(line))
    }


def test_the_scan_sees_a_card_at_all(minted):
    """Anti-vacuity. A row pattern that matched nothing would satisfy every
    token assertion below while measuring no bytes."""
    rows = _card_rows(minted)
    assert len(rows) >= 5, f"the card scan found {len(rows)} rows: {rows}"
    assert "Name" in rows, f"no Name row — the scan is not reading the card: {rows}"


def test_identity_card_carries_no_unfilled_token(minted):
    unfilled = {f: v for f, v in _card_rows(minted).items() if TOKEN.search(v)}
    assert not unfilled, (
        f"the minted persona's identity card still holds authoring tokens: {unfilled}.\n"
        "create() knows every one of these — it was handed the id, the emoji, the "
        "colour and the role, and the adapter hands it the date. A row the scaffold "
        "cannot fill does not belong in a scaffolded card (#118)."
    )


def test_the_card_holds_the_values_create_was_given(minted):
    """Absence of `{{...}}` is not presence of the truth: blanking every row
    passes the gate above and ships a card of empty cells."""
    rows = _card_rows(minted)
    assert rows.get("Name") == ADVISOR, rows
    assert rows.get("Emoji") == EMOJI, rows
    assert rows.get("Color") == COLOR, rows
    assert rows.get("Role") == ROLE, rows
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", rows.get("Joined", "")), rows
    assert rows.get("Tier") == "Advisor", (
        f"Tier reads {rows.get('Tier')!r}. The template is `applies-to: advisors` and "
        "executors take executor-identity-card.md, so the three-way menu is a choice "
        "with one option — and a shipped persona is not where a reader picks."
    )


def test_the_authoring_prompts_survive_scaffolding(minted):
    """The 4-axis voice well is the hire's WORK, not the scaffold's.

    hire.md §3a.5 validates an advisor by finding these sections; a scaffold that
    helpfully swept them away would pass every gate above and silently break the
    protocol's own admission check (#75).
    """
    prompts = [t for t in TOKEN.findall(minted) if " " in t]
    assert len(prompts) >= 8, (
        f"only {len(prompts)} authoring prompts left in the minted persona: {prompts}.\n"
        "These are the operator's to fill at enrichment. A blanket "
        "`re.sub(r'\\{\\{[^}]*\\}\\}', ...)` greens the card gate and erases the "
        "4-axis voice well that hire.md §3a.5 greps for (#75)."
    )


def test_the_template_no_longer_claims_a_lint_that_does_not_exist():
    """The closing line asserted a post-scaffold lint for as long as none existed.

    An unachievable contract is not a strict one — it is an unimplementable one, and
    nobody implements it. 'Replace ALL placeholders' cannot hold: the prose prompts
    must survive scaffolding by design. The line now names the split it always meant.
    """
    from enginelib import paths
    template = (
        Path(paths.templates_dir()) / "personality-template.md"
    ).read_text(encoding="utf-8")
    closing = [ln for ln in template.splitlines() if ln.startswith("> ")]
    assert closing, "the template lost its closing contract line entirely"
    contract = " ".join(closing)
    assert "identity card" in contract.lower(), (
        f"the closing contract does not name the half scaffolding fills: {contract!r}"
    )
