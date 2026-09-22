"""scans/code_repo.py — section 15: Code-repo awareness.

Surfaces, for the repository **this instance is about**:
  - Recent git log (last 10 commits, --oneline).
  - docs/ files that are newer than the advisor's most-recent session file.

Detection: the code repo is the git repository that CONTAINS the DATA root
(`git rev-parse --show-toplevel` from `ctx.repo_root`'s parent). It is a property of
the instance, not of the process, so no cwd can move it.

It used to be read from `os.getcwd()` with a single guard rejecting the DATA root, and
that guard excludes one wrong answer while accepting every other one (GH#314). On the
reporting instance all four advisors' briefings carried the *engine* repository's last
ten commits under the product's "Recent commits" heading, and one also named a
`docs/architecture/lifecycle.md` that exists only in the engine. Nothing marked them:
the commits are real, recent and well-formed, and a briefing is read for exactly this
— what has just landed, and is therefore already done.

Empty-state (the DATA root is not inside a git repo): returns the italic placeholder.
The placeholder is now a statement about the instance rather than about the cwd, which
is what makes it falsifiable — "no code repo in cwd" was true of a session standing in
the DATA repo of a project that plainly had one.
"""
from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from briefing.scans import ScanCtx
from enginelib.advisors import files_for_advisor

_PLACEHOLDER = "_(no code repo — the DATA root is not inside a git repository)_"

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
    """Return the git repository that contains `ai_root`, or None.

    A positive assertion: the answer must *be* the repository the instance's DATA root
    lives in. The predicate it replaces was negative — any git repo that is not the DATA
    repo — and a negative predicate over an open set admits everything it did not think
    of. Measured against the live safe-unfollow DATA root, master answered with the
    engine checkout, an engine worktree, and an unrelated library repo, depending only
    on where the process stood.

    Derived from the DATA root rather than from its *name*: `repo_root()` identifies an
    instance root by the `roster.yaml` marker precisely because the directory is not
    always called `.conclave` (VoidPay's is `ai/`), so the name test in `project_root()`
    is not a rule this can borrow. Asking git from the parent also handles a DATA root
    nested deeper than one level, which a bare `.parent` would not.

    Returns None when the DATA root is not inside a git repo, or when git is unavailable.

    There is deliberately no "and it must not be the DATA repo" guard. The old one was
    live while the cwd decided the answer — a session standing in the DATA repo is an
    ordinary thing — and it became unreachable the moment the derivation moved to the DATA
    root's parent, which by construction lies outside it. Mutation-tested: deleting that
    guard reddened nothing.

    WHAT THIS CANNOT TELL YOU: whether `ai_root` is the DATA repo's root. If
    `CONCLAVE_AI_ROOT` is pointed at a directory *below* one, the repository above the
    parent is the DATA repo, and it is returned as the code repo. Unmeasured, because no
    resolver produces that shape: `repo_root()` answers with the marker-bearing directory
    itself.
    """
    ai_root = ai_root.resolve()
    parent = ai_root.parent
    if parent == ai_root:
        return None

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=str(parent),
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    return Path(result.stdout.strip()).resolve()


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

    files = files_for_advisor(sess_dir, ctx.advisor_filter, field="advisor")
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
