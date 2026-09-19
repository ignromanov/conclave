"""Every `engine …` verb a shipped contract names must exist in the CLI (spec 117 §6).

Commissioned by forge-chro's slot decision for 117 as a precondition on the change that
lands `engine session checkpoint`: the contract line naming a verb and the verb itself
must arrive in the same commit, and the way to force that is a gate that reddens the
moment a contract names something the CLI cannot run.

Two deliberate choices about HOW it checks.

**Backticked invocations only.** A bare `engine <word> <word>` regex over this corpus
also returns prose — "engine assumes is", "engine ships exactly" — and a gate with false
positives is a gate someone switches off. The scan therefore looks only inside inline
code spans.

**Introspect the parser, do not grep the source.** GH#31's ruling on audit/doctor is that
a claim about topology must be a behavioural assertion rather than a source grep, and the
reason applies exactly here: a grep for `add_parser("checkout")` passes on a file that is
never imported, on a registration behind a false conditional, and on a verb whose module
raises at import. Building the real parser and walking its subparsers answers the question
the contract actually asks — *can a reader run this line?*
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

# Inline code spans, then invocations inside them. Split in two so the second pattern
# never has to defend against matching across a span boundary.
_SPAN = re.compile(r"`([^`\n]+)`")
_CALL = re.compile(r"\bengine\s+([a-z][a-z0-9_-]*)(?:\s+([a-z][a-z0-9_-]*))?")

# The shipped surface: what an installed instance loads. Working docs and this
# repository's own CLAUDE.md are deliberately out — they are notes, not contracts, and a
# gate that fails the suite over a note gets deleted.
#
# `docs/architecture` joined them on 2026-09-18, on evidence rather than principle. Rewriting
# its shell-era invocations by hand left three mangled verbs — `engine audit versions.sh`,
# `engine model bumpsh`, `engine audit phantom-skillssh` — that survived both a careful read and
# a regex sweep, and this gate named all three. It is descriptive rather than executable, but an
# agent orienting itself reads it the same way, and a verb that does not resolve misleads either
# way.
_CONTRACT_DIRS = ("commands", "skills", "docs/architecture")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _subparsers_action(parser) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _cli_surface() -> dict[str, set[str] | None]:
    """noun -> the second tokens the CLI accepts, or None when any token is an argument.

    `None` is not "anything goes" carelessly: it means the noun takes no sub-verbs and
    declares no `choices`, so the second word in a documented invocation is a value this
    gate has no way to validate. Saying so is the honest answer; pretending the check
    covered it would be the false-clean this suite has been bitten by before.
    """
    from engine.__main__ import _build_parser

    top = _subparsers_action(_build_parser())
    assert top is not None, "the engine parser has no subcommands — the gate is measuring nothing"

    surface: dict[str, set[str] | None] = {}
    for noun, noun_parser in top.choices.items():
        nested = _subparsers_action(noun_parser)
        if nested is not None:
            surface[noun] = set(nested.choices)
            continue
        declared = None
        for action in noun_parser._actions:
            if action.choices and not action.option_strings:
                declared = {str(c) for c in action.choices}
                break
        surface[noun] = declared
    return surface


def _documented_invocations() -> list[tuple[Path, int, str, str | None]]:
    root = _repo_root()
    found: list[tuple[Path, int, str, str | None]] = []
    for directory in _CONTRACT_DIRS:
        for path in sorted((root / directory).rglob("*.md")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for span in _SPAN.findall(line):
                    for noun, verb in _CALL.findall(span):
                        found.append((path.relative_to(root), lineno, noun, verb or None))
    return found


def test_the_gate_has_a_corpus_and_a_surface_to_check_it_against():
    """The vacuity guard.

    An empty corpus and an empty surface both make every assertion below pass. Both have
    happened to gates in this repository — a parametrize set that discovers nothing is
    SKIPPED by default, which is why `empty_parameter_set_mark = fail_at_collect` is set
    in pytest.ini — so the gate states its own denominators out loud.
    """
    surface = _cli_surface()
    corpus = _documented_invocations()
    assert len(surface) >= 20, f"only {len(surface)} nouns registered — parser did not build"
    assert len(corpus) >= 20, f"only {len(corpus)} documented invocations found — scan is broken"


def test_every_documented_engine_verb_resolves_in_the_cli():
    surface = _cli_surface()
    dangling: list[str] = []

    for path, lineno, noun, verb in _documented_invocations():
        if noun not in surface:
            dangling.append(f"{path}:{lineno} — `engine {noun}` — no such noun")
            continue
        accepted = surface[noun]
        if verb is None or accepted is None:
            continue
        if verb not in accepted:
            dangling.append(
                f"{path}:{lineno} — `engine {noun} {verb}` — "
                f"{noun} accepts {sorted(accepted)}"
            )

    assert not dangling, (
        "a shipped contract names an engine invocation that does not exist:\n  "
        + "\n  ".join(dangling)
    )


@pytest.mark.parametrize(
    "span,expected",
    [
        ("engine session close", ("session", "close")),
        ("python -m engine briefing build sage-cto", ("briefing", "build")),
        ("engine status --advisor sage-cto", ("status", None)),
        ("engine doctor", ("doctor", None)),
    ],
)
def test_the_scanner_reads_an_invocation_the_way_a_reader_does(span, expected):
    assert _CALL.findall(span)[0] == (expected[0], expected[1] or "")


@pytest.mark.parametrize(
    "line",
    [
        "the engine assumes is not a verb",
        "this engine ships exactly one binary",
        "see engine/scripts/engine/cmd/status.py",
    ],
)
def test_prose_outside_a_code_span_is_never_read_as_an_invocation(line):
    """forge-chro's measured objection to the obvious regex, kept as a test.

    The first two lines are real sentences from this corpus; a bare
    `engine <word> <word>` match returns `assumes is` and `ships exactly` from them.
    """
    assert _SPAN.findall(line) == []
