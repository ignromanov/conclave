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
"""
from __future__ import annotations

from collections.abc import Sequence

from enginelib.status.model import Absent, Freshness, Measurement, SectionResult, Severity
from enginelib.status.reduce import rank_sections

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

# Rule 7's own prescription, rendered the way it was written: age beside the verdict as
# EVIDENCE. One phrase per axis, because the axis is what makes the two readable as
# different facts rather than as one number printed twice.
_STALE_WORDS: dict[str, str] = {
    "snapshot": "снимку",
    "movement": "очередь не двигалась",
}
_UNKNOWN_WORDS: dict[str, str] = {
    "snapshot": "снимок не датирован",
    "movement": "движение не зафиксировано",
}


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


def _age_words(age) -> str:
    """An age a human reads at a glance: hours under a day, whole days above it.

    Deliberately coarse. The suffix exists so a reader can discount a reading, and
    `19ч` and `19ч 43м` support that decision identically while the second costs a
    column the glance layer does not have (rule 8: twelve lines, and the gloss wins).
    Anything under an hour still renders `1ч` rather than `0ч`, because a zero here
    would read as "no age" — the conflation rule 6 forbids, in miniature.
    """
    hours = int(age.total_seconds() // 3600)
    if hours < 24:
        return f"{max(hours, 1)}ч"
    return f"{hours // 24}д"


def freshness_suffix(freshness: Sequence[Freshness]) -> str:
    """The words a stale reading carries instead of a glyph. Empty when every axis is fresh.

    Only non-fresh axes render. A suffix on a current reading is noise: the reader is
    being handed a reason to discount the number, not a timestamp.
    """
    parts: list[str] = []
    for f in freshness:
        if f.verdict == "fresh":
            continue
        if f.verdict == "unknown":
            parts.append(_UNKNOWN_WORDS[f.axis])
        else:
            parts.append(f"{_STALE_WORDS[f.axis]} {_age_words(f.age)}")
    return "".join(f" · {p}" for p in parts)


def quantity(m: Measurement, freshness: Sequence[Freshness] = ()) -> str:
    """One measurement as the operator reads it — the ONLY place it is worded.

    It lives in the printer and not in `reduce.py` because a connective ("of" vs
    "из") is presentation, and rule 10 makes the language a property of the surface.
    A reduction that returned this string would force every other printer to either
    re-parse it or re-derive it, which is the exact defect this projection was written
    to retire: `spec_progress._process_spec` computes four numbers and hands back a
    formatted row, so no second consumer can reach them.

    The freshness suffix is appended here for the same reason (rule 7a, B3): this is
    already the one function where wording lives, so a second printer inherits the
    split instead of re-deriving it — and a builder that handed over a finished phrase
    would put presentation back in the gathering layer.
    """
    if isinstance(m, Absent):
        return f"— {m.reason}"
    denom = f" из {m.of}" if m.of is not None else ""
    return f"{m.value}{denom} {m.noun}{freshness_suffix(freshness)}"


def glance(
    speaker: str, emoji: str, surface: str, date: str, sections: Sequence[SectionResult]
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
        body.append(f"{glyph}**{s.name}**  {quantity(s.measurement, s.freshness)}".rstrip())

    head = f"{emoji} **{speaker} · {surface} · {date}**"
    lines = [_row(head), _row()] + [_row(b) for b in body]
    return "\n".join(lines)


def glance_overflows(sections: Sequence[SectionResult]) -> bool:
    """True when the glance block would exceed its twelve content lines.

    Surfaced rather than silently truncated: dropping a row to fit is how an
    inventory surface becomes 'wrong by omission and confident'. A caller over the
    budget must GROUP (rule 2's four-cluster cap), never trim.
    """
    return len(sections) > GLANCE_MAX_CONTENT_LINES


def work(sections: Sequence[SectionResult]) -> str:
    """The full layer: one section per glance row, same names, same order.

    Every measured section ends in its one-hop proof path (rule 5); every unmeasured
    one states its reason in words (rule 6). Neither is optional, which is why both
    come off the model rather than being assembled here.
    """
    out: list[str] = []
    for s in rank_sections(sections):
        out.append(f"## {s.name}")
        m = s.measurement
        out.append(quantity(m, s.freshness))
        if not isinstance(m, Absent):
            out.append("")
            out.append(f"→ пруф: {m.proof}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
