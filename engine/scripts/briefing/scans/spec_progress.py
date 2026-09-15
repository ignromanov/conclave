"""scans/spec_progress.py — section #2: Spec progress.

Parses acceptance-block checkboxes from spec.md files owned
by (or mentioning) the current advisor.  Returns N/M done; advisor-owned
boxes are flagged with ★.

Scan logic:
  1. Walk ops/specs/###-*/spec.md.
  2. For each spec whose frontmatter ``owner``, ``advisor`` or
     ``owner_suggestion`` names ctx.advisor, collect its acceptance block (any of the headings
     ``## Acceptance``, ``## N. Acceptance``, ``## Acceptance criteria``, …).
  3. Count ``- [x]`` (done) vs ``- [ ]`` (open) checkboxes.
  4. Emit one line per spec: "### N/M — <id>: <title>" with done-count.

Empty-state: _(no advisor-owned spec acceptance criteria found)_

Two layers since plan 057 T10: ``collect`` reads and CLASSIFIES, ``build`` filters and
renders. Until then this module computed four numbers per spec and handed back a
formatted row, so no second consumer could reach them — `render_terminal.quantity`
names that as the defect the whole projection exists to retire. The classification
itself is pure and lives in `enginelib.status.specs`, on the sanctioned edge
(briefing -> enginelib, never back).
"""
from __future__ import annotations

import re
from pathlib import Path

from briefing.scans import ScanCtx, _specfm
from enginelib.status.specs import SpecAcceptance, classify

_PLACEHOLDER = "_(no advisor-owned spec acceptance criteria found)_"

# Matches any acceptance-block heading. The corpus writes ten spellings of it —
# "## Acceptance", "## 4. Acceptance", "## 8. Acceptance criteria",
# "## Acceptance (draft — refined in plan)", "## 5. Acceptance and kill criteria" —
# and the old pattern (`^##\\s+acceptance criteria`) matched exactly one of them, so
# nine of the twenty-one specs carrying an acceptance block were invisible (#227).
# The section number is optional and anything after the word "acceptance" is free text.
_AC_HEADING_RE = re.compile(r"^##\s+(?:\d+\.\s*)?acceptance\b", re.IGNORECASE)
# Next level-2 heading after the AC block ends the block.
_H2_RE = re.compile(r"^##\s+")
# Checkbox lines.
_CHECKED_RE = re.compile(r"^- \[x\]", re.IGNORECASE)
_OPEN_RE = re.compile(r"^- \[ \]")

#: Where the count came from, for `Count.proof`. One hop, per state-report rule 5.
PROOF = "ops/specs/*/spec.md — блок приёмки"


def collect(ctx: ScanCtx) -> list[SpecAcceptance]:
    """Every spec in scope, each carrying the class of what could be read from it.

    In scope means: this advisor's specs under advisor scope, and **every** spec under
    instance scope — including the ones carrying no ownership field at all, which are
    returned as `unowned` rather than dropped. That asymmetry is the whole point.
    `owns(fm, advisor)` answers None for "someone else's" and for "nobody's" alike, so
    an advisor-scoped render must drop both, and an instance-scoped one must drop
    neither: an instance total that silently excludes the specs nobody claimed is a
    total over an unstated subset. Measured 2026-09-15 here, that is three specs —
    among them 086, which the whole feedback notebook rests on.
    """
    specs_root = ctx.repo_root / "ops" / "specs"
    if not specs_root.is_dir():
        return []

    rows: list[SpecAcceptance] = []
    for spec_path in sorted(specs_root.glob("*/spec.md")):
        row = _read_spec(spec_path, ctx.advisor_filter)
        if row is not None:
            rows.append(row)
    return rows


def build(ctx: ScanCtx) -> str:
    """Return spec-progress markdown for advisor-owned specs.

    Renders only the classes this section can speak a sentence about. The ones it
    drops are not lost — `collect` returns them, and `engine status` counts them —
    but widening this render is a display change and belongs to that contract's owner,
    not to the extraction that made the numbers reachable.
    """
    lines = [
        rendered
        for row in collect(ctx)
        if (rendered := _render(row, ctx.advisor_filter)) is not None
    ]
    if not lines:
        return _PLACEHOLDER
    return "\n".join(lines)


def _read_spec(spec_path: Path, advisor: str | None) -> SpecAcceptance | None:
    """Classify one spec, or None when it is out of scope for *advisor*.

    Unreadable is not a class: a spec.md that cannot be opened is a fault of this run,
    not a state of the corpus, and counting it would put a transient I/O error into a
    partition that reports on the work.
    """
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm = _specfm.parse_frontmatter(text)
    owner_field = _specfm.owns(fm, advisor)
    if owner_field is None and advisor is not None:
        # Someone else's spec, or nobody's. An advisor-scoped section drops both; only
        # instance scope can tell them apart, and only it claims to cover everything.
        return None

    spec_id = str(fm.get("id") or fm.get("spec_id") or spec_path.parent.name)
    title = str(fm.get("title") or spec_id)
    total, done, advisor_open, has_block = _count_checkboxes(text, advisor)
    klass = classify(owner_field=owner_field, has_acceptance_block=has_block, total=total)

    return SpecAcceptance(
        spec_id=spec_id,
        title=title,
        klass=klass,
        owner_field=owner_field,
        provenance=_specfm.provenance(fm),
        done=done if klass == "measured" else None,
        total=total if klass == "measured" else None,
        advisor_open=advisor_open,
    )


def _render(row: SpecAcceptance, advisor: str | None) -> str | None:
    """One briefing line, or None for a class this section does not render.

    `no_acceptance` and `unowned` return None, which is what this section did before
    the split and is left unchanged on purpose — the golden briefing net is the only
    instrument covering the extraction, and an extraction that also changes the output
    cannot be checked by it.
    """
    if row.klass == "unowned" or row.klass == "no_acceptance":
        return None
    if row.klass == "no_checkboxes":
        # Zero and absent are different states. Twelve specs declare acceptance and
        # list no checkbox under it; dropping them renders identically to owning no
        # specs at all, which is the conclusion the advisor then draws (#227).
        return (
            f"- unverifiable — **{row.spec_id}**: {row.title}{row.provenance}"
            " — acceptance block lists no checkboxes"
        )
    flag = " ★" if row.advisor_open > 0 else ""
    return f"- {row.done}/{row.total} ✓ — **{row.spec_id}**: {row.title}{row.provenance}{flag}"


def _count_checkboxes(text: str, advisor: str | None) -> tuple[int, int, int, bool]:
    """Return (total, done, advisor_open, has_block) for the acceptance block.

    ``has_block`` distinguishes "declares acceptance and lists nothing" from "declares
    no acceptance at all" — the caller renders the first and drops the second.
    """
    lines = text.splitlines()
    in_ac = False
    has_block = False
    total = done = advisor_open = 0

    for line in lines:
        if not in_ac:
            if _AC_HEADING_RE.match(line):
                in_ac = True
                has_block = True
            continue
        # End of AC block on next H2.
        if _H2_RE.match(line) and not _AC_HEADING_RE.match(line):
            break
        if _CHECKED_RE.match(line):
            total += 1
            done += 1
        elif _OPEN_RE.match(line):
            total += 1
            # Flag if line body mentions the advisor name (ownership hint). Under
            # instance scope there is no name to mention, so nothing is flagged —
            # `"" in line` would have starred every open item on the board.
            if advisor is not None and advisor in line:
                advisor_open += 1

    return total, done, advisor_open, has_block
