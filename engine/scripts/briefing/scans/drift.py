"""scans/drift.py — section #9: Drift flags.

Diffs the ``status`` field in each advisor-touched spec.md frontmatter
against the STATUS token in the corresponding REGISTRY.md row.  Flags
specs where the two disagree.

Scan logic:
  1. Parse ops/specs/REGISTRY.md — extract (spec_id → registry_status) from
     table rows ("| ### | ... | STATUS | ...").
  2. Walk ops/specs/###-*/spec.md, keeping those whose owner / advisor /
     owner_suggestion names ctx.advisor.
  3. Compare frontmatter ``status`` with REGISTRY.md STATUS cell.
  4. Emit one line per drift found.  If everything agrees → placeholder.

Empty-state: _(no spec/registry drift detected)_
"""
from __future__ import annotations

import re
from pathlib import Path

from briefing.scans import ScanCtx, _specfm
from enginelib.spec import map_status

_PLACEHOLDER = "_(no spec/registry drift detected)_"

# Matches table data rows whose first cell is a numeric spec id.
# Column layout: | # | Feature | Status | Started | Milestone | Spec |
# We split on | rather than use a complex regex, because Feature and Status
# cells contain free-form text with nested parens and dashes.
_TABLE_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|")


def build(ctx: ScanCtx) -> str:
    """Return drift-flag markdown for advisor-touched specs."""
    specs_root = ctx.repo_root / "ops" / "specs"
    registry_path = ctx.repo_root / "ops" / "specs" / "REGISTRY.md"

    if not specs_root.is_dir() or not registry_path.is_file():
        return _PLACEHOLDER

    registry_statuses = _parse_registry(registry_path)

    drifts: list[str] = []
    for spec_path in sorted(specs_root.glob("*/spec.md")):
        result = _check_drift(spec_path, ctx.advisor, registry_statuses)
        if result is not None:
            drifts.append(result)

    if not drifts:
        return _PLACEHOLDER
    return "\n".join(drifts)


def _parse_registry(registry_path: Path) -> dict[str, str]:
    """Return {spec_id_str: raw_status_cell} from REGISTRY.md table rows.

    Keyed by the numeric spec id with leading zeros stripped (e.g. "84").
    The status cell value is kept verbatim for downstream normalization.
    """
    out: dict[str, str] = {}
    try:
        text = registry_path.read_text(encoding="utf-8")
    except OSError:
        return out

    for line in text.splitlines():
        if not _TABLE_ROW_RE.match(line):
            continue
        # Split on | and strip each cell; layout is | id | feature | status | ...
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        spec_num = cells[0].lstrip("0") or "0"
        if not spec_num.isdigit():
            continue
        status_raw = cells[2].strip()
        if status_raw:
            out[spec_num] = status_raw
    return out


def _check_drift(
    spec_path: Path,
    advisor: str,
    registry_statuses: dict[str, str],
) -> str | None:
    """Return a drift line if spec status != registry status, else None."""
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm = _specfm.parse_frontmatter(text)
    if _specfm.owns(fm, advisor) is None:
        return None

    spec_id = str(fm.get("id") or fm.get("spec_id") or "")
    if not spec_id:
        return None

    fm_status = map_status(str(fm.get("status") or ""))

    # Normalize registry status: strip trailing parens/notes, then canonicalize.
    reg_raw = registry_statuses.get(spec_id.lstrip("0") or "0", "").split("(")[0].strip()
    if not reg_raw:
        # Not in registry — that's a different problem, skip silently. The emptiness
        # test is on the RAW cell: map_status("") is the token "MISSING", so asking it
        # after normalisation turns every absent row into a drift against a spec that
        # simply is not listed.
        return None
    reg_status = map_status(reg_raw)

    if fm_status == reg_status:
        return None

    title = fm.get("title") or spec_id
    return (
        f"- **DRIFT** spec {spec_id}: frontmatter=`{fm_status}` "
        f"registry=`{reg_status}` — {title}"
    )
