"""scans/spec_progress.py — section #2: Spec progress.

Parses ``## Acceptance criteria`` checkboxes from spec.md files owned
by (or mentioning) the current advisor.  Returns N/M done; advisor-owned
boxes are flagged with ★.

Scan logic:
  1. Walk ops/specs/###-*/spec.md.
  2. For each spec whose frontmatter ``advisor`` or ``owner_suggestion``
     matches ctx.advisor, collect the ## Acceptance criteria block.
  3. Count ``- [x]`` (done) vs ``- [ ]`` (open) checkboxes.
  4. Emit one line per spec: "### N/M — <id>: <title>" with done-count.

Empty-state: _(no advisor-owned spec acceptance criteria found)_
"""
from __future__ import annotations

import re
from pathlib import Path

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(no advisor-owned spec acceptance criteria found)_"

# Matches YAML frontmatter block at file top.
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Matches any ## Acceptance criteria heading (case-insensitive).
_AC_HEADING_RE = re.compile(r"^##\s+acceptance criteria", re.IGNORECASE)
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

    fm = _parse_frontmatter(text)
    if not _is_advisor_spec(fm, advisor):
        return None

    spec_id = fm.get("id") or fm.get("spec_id") or spec_path.parent.name
    title = fm.get("title") or str(spec_id)

    total, done, advisor_open = _count_checkboxes(text, advisor)
    if total == 0:
        return None

    flag = " ★" if advisor_open > 0 else ""
    return f"- {done}/{total} ✓ — **{spec_id}**: {title}{flag}"


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Return a flat dict of frontmatter key→value (string only, best-effort)."""
    m = _FM_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            out[key.strip()] = val.strip().strip('"')
    return out


def _is_advisor_spec(fm: dict[str, str], advisor: str) -> bool:
    """True if the spec's frontmatter names this advisor."""
    return (
        fm.get("advisor") == advisor
        or fm.get("owner_suggestion") == advisor
    )


def _count_checkboxes(text: str, advisor: str) -> tuple[int, int, int]:
    """Return (total, done, advisor_open) checkboxes in ## Acceptance criteria block."""
    lines = text.splitlines()
    in_ac = False
    total = done = advisor_open = 0

    for line in lines:
        if not in_ac:
            if _AC_HEADING_RE.match(line):
                in_ac = True
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

    return total, done, advisor_open
