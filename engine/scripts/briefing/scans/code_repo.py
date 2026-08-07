"""scans/code_repo.py — section 15: Code-repo awareness.

When the process cwd is a code repository (distinct from the .ai/ repo),
surfaces:
  - Recent git log (last 10 commits, --oneline).
  - docs/ files that are newer than the advisor's most-recent session file.

Detection: `git rev-parse --show-toplevel` from cwd; compare against
ctx.repo_root to exclude the .ai/ repo itself.

Empty-state (cwd is .ai/ or no code repo): returns the italic placeholder.
"""
from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from briefing.scans import ScanCtx
from enginelib.advisors import files_for_advisor

_PLACEHOLDER = "_(no code repo in cwd — running from .ai/ or non-git directory)_"

# Exclude informational meta-files that never carry meaningful change signals.
_DOCS_SKIP_STEMS = {"README", "CHANGELOG", "LICENSE", "CONTRIBUTING"}


def build(ctx: ScanCtx) -> str:
    """Return git log + new docs/ section, or the italic placeholder.

    Read-only: uses `git log` and mtime checks; no mutations.
    No live `gh` calls.
    """
    code_root = _detect_code_root(ctx.repo_root)
    if code_root is None:
        return _PLACEHOLDER

    parts: list[str] = []

    # --- recent git log ---
    log = _git_log(code_root)
    if log:
        parts.append("**Recent commits:**")
        parts.append(log)

    # --- docs/ files newer than last session ---
    since_dt = _last_session_mtime(ctx)
    docs_section = _new_docs(code_root, since_dt)
    if docs_section:
        since_label = since_dt.strftime("%Y-%m-%d") if since_dt else "beginning"
        parts.append(f"**docs/ changed since {since_label}:**")
        parts.append(docs_section)

    if not parts:
        return _PLACEHOLDER

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_code_root(ai_root: Path) -> Path | None:
    """Return the code-repo root if cwd is inside one distinct from ai_root.

    Runs `git rev-parse --show-toplevel` in the current working directory.
    Returns None when:
      - cwd is not inside any git repo,
      - the detected root equals ai_root (i.e. we are in .ai/ itself),
      - git is not available.
    """
    cwd = Path(os.getcwd()).resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    candidate = Path(result.stdout.strip()).resolve()
    if candidate == ai_root.resolve():
        return None

    return candidate


def _git_log(repo: Path, n: int = 10) -> str:
    """Return the last `n` commits as a single string (one line each)."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            capture_output=True,
            text=True,
            cwd=str(repo),
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


def _last_session_mtime(ctx: ScanCtx) -> datetime | None:
    """Return the mtime of the most-recent session file for this advisor.

    Returns None when no session files exist (fall back to showing all docs/).
    """
    sess_dir = ctx.sessions_dir
    if not sess_dir.is_dir():
        return None

    files = files_for_advisor(sess_dir, ctx.advisor, field="advisor")
    if not files:
        return None

    newest = max(files, key=lambda p: p.stat().st_mtime)
    return datetime.fromtimestamp(newest.stat().st_mtime, tz=UTC)


def _new_docs(repo: Path, since: datetime | None) -> str:
    """Return a bullet list of docs/ files modified after `since`.

    When `since` is None, returns all docs/ files (no cutoff).
    Skips subdirectories and meta-stems (_DOCS_SKIP_STEMS).
    """
    docs_dir = repo / "docs"
    if not docs_dir.is_dir():
        return ""

    entries: list[tuple[float, Path]] = []
    for f in docs_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.stem in _DOCS_SKIP_STEMS:
            continue
        mtime = f.stat().st_mtime
        if since is not None:
            file_dt = datetime.fromtimestamp(mtime, tz=UTC)
            if file_dt <= since:
                continue
        entries.append((mtime, f))

    if not entries:
        return ""

    # Newest first.
    entries.sort(key=lambda t: t[0], reverse=True)
    lines = [f"- {p.relative_to(repo)}" for _, p in entries]
    return "\n".join(lines)
