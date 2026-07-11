"""spec.py — normalize spec frontmatter. Core logic, I/O-free of stdout/argparse/exit.

Port of engine/scripts/normalize-spec-frontmatter.sh. Pure functions + file I/O only;
no print/sys.exit/argparse. The adapter (engine/cmd/spec.py) owns all I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from enginelib.snapshot import snapshot_write

_CANONICAL = frozenset(
    {"proposed", "in-progress", "in-review", "done", "superseded", "abandoned", "backlog"}
)


def map_status(raw: str) -> str:
    """Map raw status to canonical 7-value enum, 'MISSING', or 'UNKNOWN:<raw>'.

    Fast-path: already canonical → return unchanged.
    Else: lowercase + collapse runs of spaces to single dash, then map.
    UNKNOWN returns the original *raw* string (not the lowercased form).
    """
    if raw in _CANONICAL:
        return raw
    # tr '[:upper:]' '[:lower:]' | tr -s ' ' '-'
    lower = re.sub(r" +", "-", raw.lower())
    if lower == "proposed":
        return "proposed"
    if lower == "approved" or lower.startswith("design-review"):
        return "in-progress"
    if lower in ("in-progress", "active"):
        return "in-progress"
    if lower in ("in-review", "ready-for-review"):
        return "in-review"
    if lower in ("done", "complete", "completed", "merged"):
        return "done"
    if lower == "backlog":
        return "backlog"
    if lower == "superseded":
        return "superseded"
    if lower in ("abandoned", "cancelled"):
        return "abandoned"
    if lower == "ready":
        return "in-progress"
    if lower == "":
        return "MISSING"
    return f"UNKNOWN:{raw}"


@dataclass
class NormalizeResult:
    """Carries per-file inline lines, deferred report lines, and summary counts."""

    inline_lines: list[str] = field(default_factory=list)
    report_lines: list[str] = field(default_factory=list)
    files_changed: int = 0
    files_reported: int = 0


def _extract_fm_field(fm_lines: list[str], key: str) -> str:
    """Return value of the first `key: value` line in frontmatter lines.

    Strips leading whitespace from the value. Returns "" if not found.
    Mirrors the bash awk: /^key:/ { sub(/^key:[[:space:]]*/,""); print; exit }.
    No [[:space:]] requirement for matching (bash uses /^key:/ for extraction).
    """
    prefix = f"{key}:"
    for line in fm_lines:
        if line.startswith(prefix):
            return line[len(prefix):].lstrip()
    return ""


def _apply_changes(text: str, new_status: str, add_id: str, add_advisor: str) -> str:
    """Rewrite frontmatter in-place, mirroring the awk logic exactly.

    - ^status:[[:space:]] + new_status != "" → replace line
    - ^spec_id:[[:space:]] + add_id != ""   → keep line, inject `id: <add_id>` after
    - ^owner_suggestion:[[:space:]] + add_advisor != "" → keep line, inject `advisor: <add_advisor>` after
    - everything else → keep unchanged
    """
    out: list[str] = []
    fm_count = 0
    in_fm = False
    for line in text.splitlines():
        if line == "---":
            fm_count += 1
            in_fm = fm_count == 1
            out.append(line)
            continue
        if in_fm and new_status and re.match(r"^status:\s", line):
            out.append(f"status: {new_status}")
            continue
        if in_fm and add_id and re.match(r"^spec_id:\s", line):
            out.append(line)
            out.append(f"id: {add_id}")
            continue
        if in_fm and add_advisor and re.match(r"^owner_suggestion:\s", line):
            out.append(line)
            out.append(f"advisor: {add_advisor}")
            continue
        out.append(line)
    result = "\n".join(out)
    if text.endswith("\n"):
        result += "\n"
    return result


def _process_spec(file: Path, apply: bool, result: NormalizeResult) -> None:
    """Process one spec.md, accumulating inline and deferred lines into result."""
    slug = file.parent.name
    text = file.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Check for YAML frontmatter — first line must be exactly "---"
    if not lines or lines[0] != "---":
        result.report_lines.append(
            f"[NO-FRONTMATTER] {slug}: file has no YAML frontmatter"
            " — skipped (manual classification needed)"
        )
        result.files_reported += 1
        return

    # Collect frontmatter lines (between first and second "---")
    fm: list[str] = []
    for line in lines[1:]:
        if line == "---":
            break
        fm.append(line)

    raw_status = _extract_fm_field(fm, "status")
    raw_spec_id = _extract_fm_field(fm, "spec_id")
    raw_owner = _extract_fm_field(fm, "owner_suggestion")
    raw_id = _extract_fm_field(fm, "id")
    raw_advisor = _extract_fm_field(fm, "advisor")

    needs_change = False
    new_status = ""
    add_id = ""
    add_advisor = ""

    # Status normalization
    if not raw_status:
        result.report_lines.append(
            f"[MISSING-STATUS] {slug}: no status: field in frontmatter"
        )
        result.files_reported += 1
    else:
        canonical = map_status(raw_status)
        if canonical.startswith("UNKNOWN:"):
            result.report_lines.append(
                f"[UNKNOWN-STATUS] {slug}: status='{raw_status}' — not in mapping"
            )
            result.files_reported += 1
        elif canonical != raw_status:
            new_status = canonical
            needs_change = True

    # id: alias (from spec_id:)
    if raw_spec_id and not raw_id:
        add_id = raw_spec_id
        needs_change = True

    # advisor: alias (from owner_suggestion:, skip "null")
    if raw_owner and raw_owner != "null" and not raw_advisor:
        add_advisor = raw_owner
        needs_change = True

    if not needs_change:
        return

    # Inline lines (load-bearing order: WOULD-CHANGE → WOULD-ADD id → WOULD-ADD advisor → APPLIED)
    if new_status:
        result.inline_lines.append(
            f'[WOULD-CHANGE] {slug}: status "{raw_status}" → "{new_status}"'
        )
    if add_id:
        result.inline_lines.append(f"[WOULD-ADD]    {slug}: id: {add_id}")
    if add_advisor:
        result.inline_lines.append(f"[WOULD-ADD]    {slug}: advisor: {add_advisor}")

    if apply:
        new_text = _apply_changes(text, new_status, add_id, add_advisor)
        snapshot_write(file, new_text)
        result.inline_lines.append(f"[APPLIED]      {slug}")
        result.files_changed += 1


def normalize_specs(specs_dir: Path, apply: bool) -> NormalizeResult:
    """Normalize all ops/specs/*/spec.md files under specs_dir.

    Files are processed in sorted order (deterministic). Returns a NormalizeResult
    with inline change-lines, deferred report-lines, and summary counts.
    """
    spec_files = sorted(specs_dir.glob("*/spec.md")) if specs_dir.is_dir() else []
    result = NormalizeResult()
    for f in spec_files:
        _process_spec(f, apply, result)
    return result
