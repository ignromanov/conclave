"""paths.py — ops/feedback/ layout resolution for spec 086.

Imports only repo_root from briefing.paths — NOT feedback_dir or
feedback_archive_dir, which point to the OLD agent-memory/advisors/feedback/
location. This module's functions use distinct names to avoid confusion.
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
    """Empty file whose mtime is the cadence signal (resolves spec N2)."""
    return feedback_root() / "_index" / "last-triage"


def archive_dir() -> Path:
    return feedback_root() / "_archive"


def migrated_dir() -> Path:
    return feedback_root() / "_migrated"


def review_dir(date_str: str) -> Path:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        raise ValueError(f"review_dir: unsafe date_str {date_str!r}")
    return feedback_root() / date_str
