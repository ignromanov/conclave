"""paths.py — ops/feedback/ layout resolution for spec 086.

Imports only repo_root from briefing.paths. That module used to also carry
feedback_dir/feedback_archive_dir pointing at the OLD agent-memory/advisors/feedback/
location; this module never used them, nothing else did either, and they were deleted
with the tests that were their only callers (GH#105). ops/feedback/ is the one layout.
"""
from __future__ import annotations

import re
from pathlib import Path

from briefing.paths import repo_root


def feedback_root() -> Path:
    return repo_root() / "ops" / "feedback"


def index_path() -> Path:
    return feedback_root() / "_index" / "index.jsonl"


def last_triage_marker() -> Path:
    """Records when the last triage session completed — the cadence signal.

    The timestamp is the file's CONTENT, written by `feedback_triage.py
    --complete-triage`. Its mtime is not usable for this: every per-item `--set`
    writes the file too, so an mtime clock measures the last item edited. An
    existing-but-empty marker therefore means *never triaged* (spec N2)."""
    return feedback_root() / "_index" / "last-triage"


def archive_dir() -> Path:
    return feedback_root() / "_archive"


def migrated_dir() -> Path:
    return feedback_root() / "_migrated"


def review_dir(date_str: str) -> Path:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        raise ValueError(f"review_dir: unsafe date_str {date_str!r}")
    return feedback_root() / date_str
