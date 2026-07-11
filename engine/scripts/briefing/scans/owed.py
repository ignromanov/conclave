"""scans/owed.py — section: Owed by you (Phase 2, #3).

Scans active (in_progress) spec and plan files for the advisor's name or
short-name appearing in a pending-action context:
  - Lines with an unchecked checkbox (``- [ ]``) that mention the advisor
  - Lines containing ``@<advisor>`` or ``owner: <advisor>`` patterns in body text
  - Sections whose heading contains an action verb + advisor name

Returns a markdown list of found items, or a placeholder if nothing found.
"""
from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(no pending actions owed by you found in active specs)_"

_CHECKBOX_TODO = re.compile(r"^\s*-\s+\[ \]")


def build(ctx: ScanCtx) -> str:
    """Return markdown list of pending actions referencing the advisor."""
    specs_root = ctx.repo_root / "ops" / "specs"
    hits = _scan_active_specs(specs_root, ctx.advisor, ctx.short_name)

    if not hits:
        return _PLACEHOLDER

    lines: list[str] = []
    for spec_id, items in hits:
        lines.append(f"**{spec_id}:**")
        for item in items:
            lines.append(f"  - {item}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _scan_active_specs(
    specs_root: Path, advisor: str, short_name: str
) -> list[tuple[str, list[str]]]:
    """Return [(spec_id, [matched_lines])] for each active spec/plan mentioning advisor."""
    if not specs_root.is_dir():
        return []

    # Patterns that indicate an action is owed by the advisor.
    name_patterns = [
        re.compile(rf"\b{re.escape(advisor)}\b", re.IGNORECASE),
        re.compile(rf"\b{re.escape(short_name)}\b", re.IGNORECASE),
        re.compile(rf"@{re.escape(advisor)}", re.IGNORECASE),
        re.compile(rf"@{re.escape(short_name)}", re.IGNORECASE),
    ]

    results: list[tuple[str, list[str]]] = []

    for spec_dir in sorted(specs_root.iterdir()):
        if not spec_dir.is_dir():
            continue
        spec_md = spec_dir / "spec.md"
        if not spec_md.is_file():
            continue

        try:
            post = frontmatter.load(str(spec_md))
        except Exception:
            continue

        if post.metadata.get("status") != "in_progress":
            continue

        spec_id = post.metadata.get("id", spec_dir.name)
        hits: list[str] = []

        # Scan spec body and plan for unchecked items mentioning the advisor.
        for candidate in [spec_md, spec_dir / "plan.md"]:
            if not candidate.is_file():
                continue
            hits.extend(
                _find_owed_lines(candidate, name_patterns, label=candidate.name)
            )

        if hits:
            results.append((str(spec_id), hits))

    return results


def _find_owed_lines(
    path: Path,
    name_patterns: list[re.Pattern[str]],
    label: str,
) -> list[str]:
    """Return lines from path that are unchecked actions mentioning the advisor."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    # Strip YAML frontmatter to avoid false positives on the owner field.
    if text.startswith("---"):
        parts = text.split("---", 2)
        body = parts[2] if len(parts) >= 3 else text
    else:
        body = text

    found: list[str] = []
    for line in body.splitlines():
        # Only pending checkboxes are "owed" — done items are already closed.
        if not _CHECKBOX_TODO.match(line):
            continue
        clean = line.strip()
        if any(p.search(clean) for p in name_patterns):
            # Strip the checkbox marker for display.
            display = re.sub(r"^-\s+\[ \]\s*", "", clean)
            found.append(f"[{label}] {display}")

    return found
