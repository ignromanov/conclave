"""backfill.py — legacy frontmatter field migration for ~170 .ai/ ops files.

Maps legacy fields to canonical snake_case schema (spec §4):
  slug   → id
  date   → created
  by     → owner

Also injects `type` (from directory context) and `schema_version: 1` on every file.

Idempotency: files already containing `schema_version` are skipped entirely.

Default mode is dry_run=True — no files are written.
Pass dry_run=False to apply. The CLI shim (backfill-frontmatter.sh) requires
--apply AND --confirm to reach dry_run=False.

Uses read_commented() + write() from frontmatter_io so comments and key order
are preserved in files that already have comments.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from briefing.frontmatter_io import read_commented, write

# Legacy field → canonical field rename map.
_RENAMES: dict[str, str] = {
    "slug": "id",
    "date": "created",
    "by": "owner",
}

# Idempotency sentinel — if present, the file has already been migrated.
_SENTINEL = "schema_version"


@dataclass
class BackfillPlan:
    """Result of scanning a directory for files that need migration."""

    page_type: str
    total_files: int = 0
    to_migrate: list[Path] = field(default_factory=list)
    skipped: int = 0  # already-migrated count


def _needs_migration(meta: dict[str, Any]) -> bool:
    """Return True if the file has frontmatter but lacks schema_version."""
    if not meta:
        return False  # no frontmatter — not in scope
    return _SENTINEL not in meta


def _apply_legacy_renames(meta: Any) -> None:
    """Rename legacy keys in-place on a CommentedMap (or plain dict).

    Operates in-place to preserve CommentedMap comment annotations.
    Deletion + insertion preserves ruamel ordering (new key appended).
    """
    for old_key, new_key in _RENAMES.items():
        if old_key in meta and new_key not in meta:
            value = meta[old_key]
            del meta[old_key]
            meta[new_key] = value


def _inject_required(meta: Any, page_type: str) -> None:
    """Inject `type` and `schema_version: 1` if absent."""
    if "type" not in meta:
        # Insert at position 0 so `type` is always first.
        # CommentedMap supports insert(index, key, value).
        if hasattr(meta, "insert"):
            meta.insert(0, "type", page_type)
        else:
            meta["type"] = page_type

    if _SENTINEL not in meta:
        meta[_SENTINEL] = 1


def plan_dir(directory: Path, *, page_type: str) -> BackfillPlan:
    """Scan directory for .md files that need migration; return a BackfillPlan.

    Does NOT write any files.
    """
    plan = BackfillPlan(page_type=page_type)

    if not directory.is_dir():
        return plan

    for md_file in sorted(directory.glob("*.md")):
        plan.total_files += 1
        try:
            meta, _ = read_commented(md_file)
        except Exception:
            # Skip files with unparseable YAML (e.g. JSONL-style feedback files).
            plan.skipped += 1
            continue
        if _needs_migration(meta):
            plan.to_migrate.append(md_file)
        else:
            plan.skipped += 1

    return plan


def backfill_dir(directory: Path, *, page_type: str, dry_run: bool = True) -> BackfillPlan:
    """Migrate legacy frontmatter fields in all .md files under directory.

    dry_run=True (default): scan and return the plan; no files written.
    dry_run=False: apply migrations; idempotent (skips already-migrated files).
    """
    plan = plan_dir(directory, page_type=page_type)

    if dry_run:
        return plan

    for md_file in plan.to_migrate:
        meta, body = read_commented(md_file)
        _apply_legacy_renames(meta)
        _inject_required(meta, page_type)
        write(md_file, meta, body)

    return plan


# ---------------------------------------------------------------------------
# Top-level entry point used by the __main__ CLI and backfill-frontmatter.sh
# ---------------------------------------------------------------------------

# Directory → page_type mapping for the standard .ai/ tree.
# Paths are relative to repo_root().
_DIR_TYPE_MAP: dict[str, str] = {
    "agent-memory/advisors/decisions": "decision",
    "agent-memory/advisors/sessions": "session",
    "agent-memory/advisors/mentions": "mention",
    # feedback/ files are JSONL, not markdown — excluded from backfill
    "ops/handoffs": "handoff",
    "ops/specs": "spec",
    "ops/open-questions": "open-question",
    "ops/retros": "retro",
    "ops/meetings": "meeting",
}


def backfill_tree(repo_root: Path, *, dry_run: bool = True) -> list[BackfillPlan]:
    """Run backfill across all known typed directories under repo_root.

    Returns a list of BackfillPlan objects (one per directory).
    """
    plans: list[BackfillPlan] = []
    for rel_dir, page_type in _DIR_TYPE_MAP.items():
        directory = repo_root / rel_dir
        plan = backfill_dir(directory, page_type=page_type, dry_run=dry_run)
        plans.append(plan)
    return plans
