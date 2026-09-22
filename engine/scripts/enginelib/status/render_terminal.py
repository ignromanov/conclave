"""status/render_terminal.py — printer #1 over the projection. Pure: string in, string out.

Spec 115 rule 11 names three printers over one model; this is the terminal one. It is
deliberately thin and obviously replaceable, because **the display contract is not the
read-model's to invent**: `state-report.md` already fixes what this surface shows,
in what hierarchy, and how it signals state. This module implements that contract and
authors none of it. Changes to what is displayed belong to the contract, and to its
owner, not here.

Two layers, per §Shape:
  1. glance — one ▍-block, at most 12 content lines, the table of contents.
  2. work   — one `##` section per glance row, same names, same order.

The glance layer carries no coordinates (rule 8): a filename may appear as a noun, a
line number may not. Citations live in the work sections, because glosses and
coordinates compete for the same twelve lines and rule 4 gives the line to the gloss.

**Two axes, two carriers** (rules 7a/7b, contract v1.1). Content severity takes the
glyph; freshness takes words in the value cell. This module used to map `Verdict` — an
enum whose every member is a statement about time — onto the glyph set
`output-formatting.md` §2 defines as content severity, and the surface inverted: the
best state a slot can hold wore the blocking glyph because a snapshot had aged, while a
slot at 27 % carried no glyph at all because its index was current. Neither glyph was
about what its number said, and each row read fine on its own.

**One language, chosen here** (rule 10). Every word this module emits comes from a
catalog passed in by the caller, defaulting to the canonical English one. Nothing in
the model is already worded, so a second printer over the same projection can render a
different language without re-deriving a single phrase — which was impossible while the
gathering adapter handed over finished prose.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from enginelib.status.model import Absent, Freshness, Measurement, Phrase, SectionResult, Severity
from enginelib.status.reduce import rank_sections
from enginelib.status.words import EN, Catalog, say

GLANCE_MAX_CONTENT_LINES = 12

# The functional glyph set — output-formatting §2. Nothing else is a signal.
_GUTTER = "▍"

# Rule 7a: the glyph column carries CONTENT severity and nothing else. A slot nobody
# has judged (`severity is None`) renders no glyph — the honest state, and not `ok`.
_MARK: dict[Severity, str] = {
    "error": "✗ ",
    "warn": "⚠ ",
    "ok": "",
}

# Rule 7a ruling 1: an instrument that never ran is always a deviation and keeps `⚠`.
# That is a fact about the system rather than about the reading's age, so it survives
# the split — and it is the one case where the glyph does not come from `severity`.
_ABSENT_MARK = "⚠ "

# The separator between a value and each freshness clause. Punctuation, not language:
# it is the same mark in every catalog, so it stays a constant rather than a phrase.
_FRESHNESS_SEP = " · "


def _row(text: str = "") -> str:
    return _GUTTER if not text else f"{_GUTTER} {text}"


def mark(section: SectionResult) -> str:
    """The glyph for one section: content severity, or `⚠` for an instrument that did
    not run. Never freshness — that leaves as words, via `freshness_suffix`."""
    if isinstance(section.measurement, Absent):
        return _ABSENT_MARK
    if section.severity is None:
        return ""
    return _MARK[section.severity]


def _age_words(age: timedelta, words: Catalog = EN) -> str:
    """An age a human reads at a glance: hours under a day, whole days above it.

    Deliberately coarse. The suffix exists so a reader can discount a reading, and
    `19h` and `19h 43m` support that decision identically while the second costs a
    column the glance layer does not have (rule 8: twelve lines, and the gloss wins).
    Anything under an hour still renders `1h` rather than `0h`, because a zero here
    would read as "no age" — the conflation rule 6 forbids, in miniature.
    """
    hours = int(age.total_seconds() // 3600)
    if hours < 24:
        return say(Phrase("age.hours", {"count": max(hours, 1)}), words)
    return say(Phrase("age.days", {"count": hours // 24}), words)


def freshness_suffix(freshness: Sequence[Freshness], words: Catalog = EN) -> str:
    """The words a stale reading carries instead of a glyph. Empty when every axis is fresh.

    Only non-fresh axes render. A suffix on a current reading is noise: the reader is
    being handed a reason to discount the number, not a timestamp.

    The catalog key carries the axis (`freshness.snapshot.stale`), so a language that
    needs a different construction per axis gets one, and an axis added to the model
    fails loudly on a missing key rather than rendering as the other one.
    """
    parts: list[str] = []
    for f in freshness:
        if f.verdict == "fresh":
            continue
        if f.verdict == "unknown":
            parts.append(say(Phrase(f"freshness.{f.axis}.unknown"), words))
        else:
            assert f.age is not None  # enforced by Freshness.__post_init__
            parts.append(
                say(
                    Phrase(f"freshness.{f.axis}.stale", {"age": _age_words(f.age, words)}),
                    words,
                )
            )
    return "".join(f"{_FRESHNESS_SEP}{p}" for p in parts)


def quantity(
    m: Measurement, freshness: Sequence[Freshness] = (), words: Catalog = EN
) -> str:
    """One measurement as the operator reads it — the ONLY place it is worded.

    That claim used to be false. `Count.noun` was a `str` assembled in the gathering
    adapter, so half of every value cell arrived pre-worded and this function only
    supplied the connective; a second printer could not have changed the language
    without re-deriving the noun. The model now carries `Phrase`, and the whole cell —
    connective, noun, denominator, freshness clause — is worded here and nowhere else.

    The assembly itself is a template rather than an f-string because word order is
    not universal: a catalog that needs the denominator elsewhere in the cell moves it
    in `quantity.measured`, without a second printer being rewritten.
    """
    if isinstance(m, Absent):
        return say(Phrase("quantity.absent", {"reason": m.reason}), words)
    denominator = (
        "" if m.of is None else say(Phrase("quantity.denominator", {"of": m.of}), words)
    )
    return say(
        Phrase(
            "quantity.measured",
            {
                "value": m.value,
                "denominator": denominator,
                "noun": m.noun,
                "freshness": freshness_suffix(freshness, words),
            },
        ),
        words,
    )


def glance(
    speaker: str,
    emoji: str,
    surface: Phrase,
    date: str,
    sections: Sequence[SectionResult],
    words: Catalog = EN,
) -> str:
    """The ≤12-line block. Ranked by urgency, never by input order.

    Rule 1: line 1 is the speaker anchor — an advisor's conclusions are never
    unattributed. Rule 3: a clean section still gets a line; on an inventory surface
    the zero IS the answer, so nothing is omitted for being empty.
    """
    ranked = rank_sections(sections)

    body: list[str] = []
    for s in ranked:
        glyph = mark(s)
        name = say(s.name, words)
        body.append(f"{glyph}**{name}**  {quantity(s.measurement, s.freshness, words)}".rstrip())

    head = f"{emoji} **{speaker} · {say(surface, words)} · {date}**"
    lines = [_row(head), _row()] + [_row(b) for b in body]
    return "\n".join(lines)


def glance_overflows(sections: Sequence[SectionResult]) -> bool:
    """True when the glance block would exceed its twelve content lines.

    Surfaced rather than silently truncated: dropping a row to fit is how an
    inventory surface becomes 'wrong by omission and confident'. A caller over the
    budget must GROUP (rule 2's four-cluster cap), never trim.
    """
    return len(sections) > GLANCE_MAX_CONTENT_LINES


def work(sections: Sequence[SectionResult], words: Catalog = EN) -> str:
    """The full layer: one section per glance row, same names, same order.

    Every measured section ends in its one-hop proof path (rule 5); every unmeasured
    one states its reason in words (rule 6). Neither is optional, which is why both
    come off the model rather than being assembled here.
    """
    out: list[str] = []
    for s in rank_sections(sections):
        out.append(f"## {say(s.name, words)}")
        m = s.measurement
        out.append(quantity(m, s.freshness, words))
        if not isinstance(m, Absent):
            out.append("")
            out.append(say(Phrase("work.proof", {"proof": m.proof}), words))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
