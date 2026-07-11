"""scans/current_work.py — section: Current Work (Phase 2, #1).

Surfaces:
- Active spec/plan from frontmatter ``status: in_progress``
- Plan checkbox progress (``- [x]`` / ``- [ ]`` counts)
- Next unchecked task
- Last commits with parsed task-IDs (from git-cache or live git log)
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import frontmatter

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(no active work detected)_"

# Matches ``- [ ] text`` and ``- [x] text`` (case-insensitive x).
_CHECKBOX_DONE = re.compile(r"^\s*-\s+\[x\]", re.IGNORECASE)
_CHECKBOX_TODO = re.compile(r"^\s*-\s+\[ \]")

# Conventional commit task-ID pattern: e.g. ``084``, ``T1.3``, ``2.1``.
_TASK_ID = re.compile(r"\b(T?\d+\.\d+|\d{3,})\b")

_MAX_COMMITS = 5


def build(ctx: ScanCtx) -> str:
    """Return a markdown summary of current active work for the advisor."""
    specs_root = ctx.repo_root / "ops" / "specs"
    active = _find_active_specs(specs_root, ctx.advisor)

    sections: list[str] = []

    if active:
        for spec_path, plan_path in active:
            sections.append(_render_active_item(spec_path, plan_path))
    else:
        sections.append(_PLACEHOLDER)

    commits_block = _render_commits(ctx.repo_root)
    if commits_block:
        sections.append(commits_block)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_active_specs(
    specs_root: Path, advisor: str
) -> list[tuple[Path, Path | None]]:
    """Return (spec_path, plan_path|None) pairs where spec status==in_progress."""
    if not specs_root.is_dir():
        return []

    results: list[tuple[Path, Path | None]] = []
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
        status = post.metadata.get("status", "")
        if status != "in_progress":
            continue
        # Optionally filter by advisor ownership.
        owner = post.metadata.get("owner", "") or post.metadata.get("advisor", "")
        if advisor and owner and advisor not in str(owner):
            continue
        plan_md = spec_dir / "plan.md"
        results.append((spec_md, plan_md if plan_md.is_file() else None))

    return results


def _render_active_item(spec_path: Path, plan_path: Path | None) -> str:
    """Render one active spec + its plan checkbox progress."""
    try:
        post = frontmatter.load(str(spec_path))
    except Exception:
        return f"- {spec_path.parent.name} _(frontmatter parse error)_"

    title = post.metadata.get("title", spec_path.parent.name)
    spec_id = post.metadata.get("id", spec_path.parent.name)

    lines: list[str] = [f"**{spec_id}** — {title}"]

    if plan_path is not None:
        done, total, next_task = _parse_checkboxes(plan_path)
        if total > 0:
            lines.append(f"  - Progress: {done}/{total} tasks done")
            if next_task:
                # Trim leading checkbox marker from the display text.
                task_text = _CHECKBOX_TODO.sub("", next_task).strip()
                lines.append(f"  - Next: {task_text}")
        else:
            lines.append("  - Plan: no checkboxes found")

    return "\n".join(lines)


def _parse_checkboxes(plan_path: Path) -> tuple[int, int, str]:
    """Return (done_count, total_count, next_unchecked_line) from plan checkboxes."""
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError:
        return 0, 0, ""

    done = 0
    total = 0
    next_task = ""

    for line in text.splitlines():
        if _CHECKBOX_DONE.match(line):
            done += 1
            total += 1
        elif _CHECKBOX_TODO.match(line):
            total += 1
            if not next_task:
                next_task = line

    return done, total, next_task


def _render_commits(repo_root: Path) -> str:
    """Return last N git commits as a markdown list with parsed task-IDs.

    Tries git-cache first (agent-memory/git-cache/log.md), falls back to a
    live ``git log`` call (read-only, safe).
    """
    log_lines = _read_git_cache(repo_root)
    if not log_lines:
        log_lines = _run_git_log(repo_root)

    if not log_lines:
        return ""

    items: list[str] = []
    for raw in log_lines[:_MAX_COMMITS]:
        raw = raw.strip()
        if not raw:
            continue
        task_ids = _TASK_ID.findall(raw)
        suffix = f" _(tasks: {', '.join(task_ids)})_" if task_ids else ""
        items.append(f"- {raw}{suffix}")

    if not items:
        return ""
    return "**Recent commits:**\n" + "\n".join(items)


def _read_git_cache(repo_root: Path) -> list[str]:
    """Read pre-fetched git log lines from agent-memory/git-cache/log.md."""
    cache = repo_root / "agent-memory" / "git-cache" / "log.md"
    if not cache.is_file():
        return []
    text = cache.read_text(encoding="utf-8")
    # Strip frontmatter if present.
    if text.startswith("---"):
        parts = text.split("---", 2)
        text = parts[2] if len(parts) >= 3 else text
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    return lines


def _run_git_log(repo_root: Path) -> list[str]:
    """Run git log --oneline -N from repo_root. Returns [] on any failure."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{_MAX_COMMITS}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        return [ln for ln in result.stdout.splitlines() if ln.strip()]
    except Exception:
        return []
