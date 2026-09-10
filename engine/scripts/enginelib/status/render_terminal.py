"""status/render_terminal.py — printer #1 over the projection. Pure: string in, string out.

Spec 115 rule 11 names three printers over one model; this is the terminal one. It is
deliberately thin and obviously replaceable, because **the display contract is not the
read-model's to invent**: `state-report.md` v1.0 already fixes what this surface shows,
in what hierarchy, and how it signals state. This module implements that contract and
authors none of it. Changes to what is displayed belong to the contract, and to its
owner, not here.

Two layers, per §Shape:
  1. glance — one ▍-block, at most 12 content lines, the table of contents.
  2. work   — one `##` section per glance row, same names, same order.

The glance layer carries no coordinates (rule 8): a filename may appear as a noun, a
line number may not. Citations live in the work sections, because glosses and
coordinates compete for the same twelve lines and rule 4 gives the line to the gloss.
"""
from __future__ import annotations

from collections.abc import Sequence

from enginelib.status.model import Absent, Measurement, SectionResult, Verdict
from enginelib.status.reduce import rank_sections

GLANCE_MAX_CONTENT_LINES = 12

# The functional glyph set — output-formatting §2. Nothing else is a signal.
_GUTTER = "▍"
_MARK: dict[Verdict, str] = {
    "unknown": "⚠ ",
    "stale_error": "✗ ",
    "stale_warn": "⚠ ",
    "fresh": "",
}


def _row(text: str = "") -> str:
    return _GUTTER if not text else f"{_GUTTER} {text}"


def quantity(m: Measurement) -> str:
    """One measurement as the operator reads it — the ONLY place it is worded.

    It lives in the printer and not in `reduce.py` because a connective ("of" vs
    "из") is presentation, and rule 10 makes the language a property of the surface.
    A reduction that returned this string would force every other printer to either
    re-parse it or re-derive it, which is the exact defect this projection was written
    to retire: `spec_progress._process_spec` computes four numbers and hands back a
    formatted row, so no second consumer can reach them.
    """
    if isinstance(m, Absent):
        return f"— {m.reason}"
    denom = f" из {m.of}" if m.of is not None else ""
    return f"{m.value}{denom} {m.noun}"


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
        mark = _MARK[s.verdict]
        body.append(f"{mark}**{s.name}**  {quantity(s.measurement)}".rstrip())

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
        out.append(quantity(m))
        if not isinstance(m, Absent):
            out.append("")
            out.append(f"→ пруф: {m.proof}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
