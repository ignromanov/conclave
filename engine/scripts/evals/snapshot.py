"""snapshot.py — the state a predicate is allowed to read.

Effect-side observation only. The agent's transcript is not in here, by design: a scorer that
reads what the agent *said* it did is an LLM judge with extra steps, and spec 104 §2.1 forbids one.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA = ".conclave"
FEEDBACK_DIR = f"{DATA}/ops/feedback"
ARCHIVE_DIR = f"{FEEDBACK_DIR}/_archive"
SPECS_DIR = f"{DATA}/ops/specs"
BRIEFINGS_DIR = f"{DATA}/agent-memory/advisors/briefings"
SESSIONS_DIR = f"{DATA}/agent-memory/advisors/sessions"
RUNLOG_DIR = f"{DATA}/agent-memory/run-log"
SKILL_PREFIXES = ("skills/", "engine/skills/", "agents/")

_FEEDBACK_ID_RE = re.compile(r"^feedback_id:\s*(\S+)\s*$", re.MULTILINE)
_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv"}


@dataclass(frozen=True)
class Snapshot:
    files: dict[str, str]            # relpath -> sha256
    reviews: dict[str, str]          # relpath of a review .md -> its feedback_id
    # feedback_id -> (item count, body length) of the SOURCE review, captured before the agent runs.
    # This is what "the record" means for the anchor predicate: an archive row preserves a record iff
    # it still carries what the source held. Comparing against the source is the only way to tell
    # "archived into a husk" (content lost) from "archived a review that had no body prose" (nothing
    # to lose) — and v1 could not, because it only asked whether the row's `body` key was truthy.
    review_content: dict[str, tuple[int, int]]
    archive_rows: dict[str, dict]    # feedback_id -> the archive row
    runlog_scripts: tuple[str, ...]  # the `script` field of every run-log row


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_content(text: str) -> tuple[int, int]:
    """(item count, body length) of a review markdown — what an archive row must preserve."""
    n_items = len(re.findall(r"^\s*-\s+id:\s*\S+", text, re.MULTILINE))
    parts = text.split("---", 2)
    body = parts[2].strip() if len(parts) > 2 else ""
    return n_items, len(body)


def take(root: Path) -> Snapshot:
    files: dict[str, str] = {}
    reviews: dict[str, str] = {}
    review_content: dict[str, tuple[int, int]] = {}
    archive_rows: dict[str, dict] = {}
    runlog: list[str] = []

    for path in root.rglob("*"):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(root))
        try:
            files[rel] = _sha256(path)
        except OSError:
            continue

        if rel.startswith(f"{FEEDBACK_DIR}/") and rel.endswith(".md") and "_archive" not in rel:
            text = path.read_text(encoding="utf-8", errors="ignore")
            m = _FEEDBACK_ID_RE.search(text)
            if m:
                reviews[rel] = m.group(1)
                review_content[m.group(1)] = _review_content(text)

        elif rel.startswith(f"{ARCHIVE_DIR}/") and rel.endswith(".jsonl"):
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fid = row.get("feedback_id")
                if fid:
                    archive_rows[fid] = row

        elif rel.startswith(f"{RUNLOG_DIR}/") and rel.endswith(".jsonl"):
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    runlog.append(str(json.loads(line).get("script", "")))
                except json.JSONDecodeError:
                    continue

    return Snapshot(
        files=files,
        reviews=reviews,
        review_content=review_content,
        archive_rows=archive_rows,
        runlog_scripts=tuple(runlog),
    )
