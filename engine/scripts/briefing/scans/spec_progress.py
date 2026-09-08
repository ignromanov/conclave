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
"""
from __future__ import annotations

import re
from pathlib import Path

from briefing.scans import ScanCtx, _specfm

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


def build(ctx: ScanCtx) -> str:
    """Return spec-progress markdown for advisor-owned specs."""
    specs_root = ctx.repo_root / "ops" / "specs"
    if not specs_root.is_dir():
        return _PLACEHOLDER

    lines: list[str] = []
    for spec_path in sorted(specs_root.glob("*/spec.md")):
        result = _process_spec(spec_path, ctx.advisor)
        if result is not None:
            lines.append(result)

    if not lines:
        return _PLACEHOLDER
    return "\n".join(lines)


def _process_spec(spec_path: Path, advisor: str) -> str | None:
    """Return a summary line for this spec if it belongs to the advisor, else None."""
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm = _specfm.parse_frontmatter(text)
    if _specfm.owns(fm, advisor) is None:
        return None
    prov = _specfm.provenance(fm)

    spec_id = fm.get("id") or fm.get("spec_id") or spec_path.parent.name
    title = fm.get("title") or str(spec_id)

    total, done, advisor_open, has_block = _count_checkboxes(text, advisor)
    if not has_block:
        # No acceptance heading at all: the spec makes no verifiable claim to report on.
        return None
    if total == 0:
        # Zero and absent are different states. Twelve specs declare acceptance and
        # list no checkbox under it; dropping them renders identically to owning no
        # specs at all, which is the conclusion the advisor then draws (#227).
        return (
            f"- unverifiable — **{spec_id}**: {title}{prov}"
            " — acceptance block lists no checkboxes"
        )

    flag = " ★" if advisor_open > 0 else ""
    return f"- {done}/{total} ✓ — **{spec_id}**: {title}{prov}{flag}"


def _count_checkboxes(text: str, advisor: str) -> tuple[int, int, int, bool]:
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
            # Flag if line body mentions the advisor name (ownership hint).
            if advisor in line:
                advisor_open += 1

    return total, done, advisor_open, has_block
