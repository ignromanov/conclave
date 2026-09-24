"""Which blocks of an auto-loaded file are closed: a worklist for a human or agent rotating it.

Nothing here moves text. Rotation is judgement under the project's own rules (one writer, read
the target first, prefer deleting what a briefing regenerates); what is mechanical is finding
the blocks that say they are closed or cite only closed work (spec 110 rotation slice, GH#369).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_HEADING = re.compile(r"^(##|###) (.*)$")
_REF = re.compile(r"(?<![\w/])(?:GH|PR )?#(\d{1,5})\b")
_CLOSED = re.compile(r"\b(closed|merged|retired|shipped|superseded|done)\b|✅", re.I)
_MARKERS = ("⛔", "⚠️", "corrected", "superseded", "refuted",
            "Устарело", "Исправлено", "опровергнуто", "Разворот", "Обновлено")
_ORDER = {"candidate": 0, "unknown": 1, "keep": 2, "no-signal": 3}

Verdict = Literal["candidate", "keep", "unknown", "no-signal"]


@dataclass(frozen=True)
class Block:
    heading: str
    line: int  # 1-based line of the heading (1 for the preamble)
    size: int  # bytes, heading included
    refs: tuple[int, ...]
    corrections: int


@dataclass(frozen=True)
class Row:
    block: Block
    verdict: Verdict
    reason: str


def blocks(text: str) -> list[Block]:
    """Split on `##`/`###` headings; text before the first one is the `(preamble)` block."""
    out: list[Block] = []
    heading, start = "(preamble)", 1
    buf: list[str] = []

    def flush() -> None:
        body = "".join(buf)
        if body or heading != "(preamble)":
            refs = tuple(dict.fromkeys(int(n) for n in _REF.findall(body)))
            marks = sum(body.count(m) for m in _MARKERS)
            out.append(Block(heading, start, len(body.encode()), refs, marks))

    for i, line in enumerate(text.splitlines(keepends=True), start=1):
        m = _HEADING.match(line.rstrip("\n"))
        if m:
            flush()
            heading, start, buf = m.group(2).strip(), i, []
        buf.append(line)
    flush()
    return out


def classify(block: Block, states: dict[int, str] | None) -> Row:
    """Verdict for one block. `states` None means GitHub could not be asked."""
    if block.heading == "(preamble)":
        return Row(block, "no-signal", "preamble — never rotated")
    known = {n: (states or {}).get(n) for n in block.refs}
    open_refs = [n for n, s in known.items() if s == "OPEN"]
    if open_refs:
        return Row(block, "keep", "cites open work: " + ", ".join(f"#{n} OPEN" for n in open_refs))
    self_closed = bool(_CLOSED.search(block.heading))
    # An unread ref may be the open remainder a "closed" heading still carries, so a heading's
    # own claim never outranks a reading that did not happen.
    if block.refs and (states is None or any(s is None for s in known.values())):
        claim = "heading says closed, but " if self_closed else ""
        return Row(block, "unknown", claim + "cites refs whose state could not be read")
    all_closed = bool(block.refs) and all(s in ("CLOSED", "MERGED") for s in known.values())
    if self_closed or all_closed:
        why = "heading says closed" if self_closed else f"all {len(block.refs)} cited refs closed"
        if block.corrections:
            why += f"; move to the archive, never delete ({block.corrections} correction markers)"
        return Row(block, "candidate", why)
    return Row(block, "no-signal", "no closure word, no cited refs")


def worklist(text: str, states: dict[int, str] | None) -> list[Row]:
    """Candidates first, then unknown, keep, no-signal; each group largest first."""
    rows = [classify(b, states) for b in blocks(text)]
    return sorted(rows, key=lambda r: (_ORDER[r.verdict], -r.block.size))
