"""validate.py — per-type required/enum/line-cap frontmatter validator.

Severity tiers (spec §3 A5):
  WARN  — soft advisory, exit 0 (frontmatter ≥10 lines)
  ERROR — hard failure, exit 1 (missing required fields, bad enum, ≥20 lines)

Consumers call validate_file(path) -> list[Finding].
validate_tree(root) walks agent-memory/ + ops/ and aggregates all findings.
`briefings/` is excluded from validation (compiled output per spec §4).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from briefing.frontmatter_io import read
from briefing.schema import PAGE_TYPES

# Frontmatter line thresholds (spec §3 A5, research R6b).
_WARN_AT = 10
_ERROR_AT = 20


class Severity(enum.Enum):
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Finding:
    path: Path
    severity: Severity
    message: str

    def __str__(self) -> str:
        return f"{self.severity.value}: {self.path}: {self.message}"


def _count_frontmatter_lines(path: Path) -> int:
    """Count lines between the opening and closing --- delimiters."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return 0
    count = 0
    for line in lines[1:]:
        if line.strip() == "---":
            break
        count += 1
    return count


def validate_file(path: Path) -> list[Finding]:
    """Validate frontmatter of a single markdown file.

    Returns a list of Finding objects (may be empty for a clean file).
    """
    findings: list[Finding] = []

    meta, _ = read(path)

    if not meta:
        # No frontmatter — not an error for arbitrary markdown files, but we
        # cannot validate type. Skip silently (the validator is opt-in per tree walk).
        return findings

    # --- line-cap check (before type validation so it always runs) ---
    fm_lines = _count_frontmatter_lines(path)
    if fm_lines >= _ERROR_AT:
        findings.append(Finding(
            path=path,
            severity=Severity.ERROR,
            message=f"frontmatter is {fm_lines} lines (hard cap: {_ERROR_AT})",
        ))
    elif fm_lines >= _WARN_AT:
        findings.append(Finding(
            path=path,
            severity=Severity.WARN,
            message=f"frontmatter is {fm_lines} lines (soft cap: {_WARN_AT})",
        ))

    # --- type field check ---
    page_type = meta.get("type")
    if not page_type:
        findings.append(Finding(
            path=path,
            severity=Severity.ERROR,
            message="missing required field: type",
        ))
        return findings

    model_cls = PAGE_TYPES.get(str(page_type))
    if model_cls is None:
        findings.append(Finding(
            path=path,
            severity=Severity.ERROR,
            message=f"unknown type: '{page_type}' (not in PAGE_TYPES registry)",
        ))
        return findings

    # --- pydantic schema validation ---
    try:
        # Handoff uses `from` as alias for `from_`; pass by_alias=False so
        # the raw frontmatter dict (which uses `from`) is accepted.
        model_cls.model_validate(meta)
    except ValidationError as exc:
        for error in exc.errors():
            loc = ".".join(str(part) for part in error["loc"])
            findings.append(Finding(
                path=path,
                severity=Severity.ERROR,
                message=f"validation error at '{loc}': {error['msg']}",
            ))

    return findings


def validate_tree(root: Path) -> list[Finding]:
    """Walk agent-memory/ + ops/ under root and validate every .md file.

    Excludes briefings/ (compiled output) per spec §4 / research R6d.
    """
    findings: list[Finding] = []
    scan_dirs = [root / "agent-memory", root / "ops"]

    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for md_file in sorted(scan_dir.rglob("*.md")):
            # Skip compiled briefings — they have no frontmatter schema.
            if "briefings" in md_file.parts:
                continue
            findings.extend(validate_file(md_file))

    return findings
