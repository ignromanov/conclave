"""enginelib.lifecycle.git_fetch — TTL-cached git-state snapshot writer.

Contract: no stdout, no argparse, no sys.exit.
Subprocess (git) + clock + file I/O are allowed (see enginelib/gh.py for precedent).
Port of lifecycle/git-fetch.sh.

run(no_cache=False) -> "hit" | "refreshed" | "lock-error"
  "hit"        — valid cache exists and TTL not exceeded; no write.
  "refreshed"  — snapshot written (or force-rewritten with no_cache=True).
  "lock-error" — could not acquire mkdir-lock within 10s timeout.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
from datetime import UTC, datetime

from enginelib import snapshot
from enginelib.lock import LockTimeout, lock_path_for, with_lock
from enginelib.paths import consumer_git_cwd, ensure_dir, git_cache_dir


def run(no_cache: bool = False) -> str:
    """Snapshot git state to a TTL-cached state.md under git_cache_dir().

    Returns a status string: "hit", "refreshed", or "lock-error".

    Every `git` call below runs in `consumer_git_cwd()`, never the inherited process cwd.
    This snapshot is written into the CONSUMER's DATA tree, so it must describe the
    consumer's repository: session_init launches this verb with cwd=engine/scripts, and
    unpinned that made the cache report the ENGINE's branch and the maintainer's absolute
    worktree paths to every consumer. Same resolver as `gh-fetch`'s repo-scope fallback.
    """
    ttl = int(os.environ.get("SNAPSHOT_GIT_TTL", "60"))
    git_cwd = consumer_git_cwd()
    cache_path = git_cache_dir() / "state.md"
    ensure_dir(cache_path.parent)

    # First hit check (no lock needed — read-only).
    if not no_cache and not snapshot.snapshot_is_stale(cache_path, ttl):
        return "hit"

    # Take the fetch lock: one refresh at a time, and a caller that can degrade.
    # Lock under LOCK_DIR, not beside the cache. The old `{cache}.lock` was a
    # DIRECTORY carrying no owner: a fetch killed mid-flight left it behind and every
    # later session waited out the full timeout on a holder that no longer existed.
    lock = contextlib.ExitStack()
    try:
        lock.enter_context(with_lock(lock_path_for(cache_path), timeout=10))
    except LockTimeout:
        return "lock-error"

    try:
        # Re-check after acquiring lock (another process may have refreshed).
        if not no_cache and not snapshot.snapshot_is_stale(cache_path, ttl):
            return "hit"

        # TRIPWIRE — sole git status call site in lifecycle/
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=git_cwd,
            )
            uncommitted = len(res.stdout.splitlines()) if res.returncode == 0 else 0
        except Exception:
            uncommitted = 0

        # TRIPWIRE — sole git worktree call site in lifecycle/
        try:
            res = subprocess.run(
                ["git", "worktree", "list"],
                capture_output=True,
                text=True,
                cwd=git_cwd,
            )
            worktree_list = res.stdout.rstrip("\n") if res.returncode == 0 else "unavailable"
        except Exception:
            worktree_list = "unavailable"

        # TRIPWIRE — sole git symbolic-ref call site in lifecycle/
        try:
            res = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=git_cwd,
            )
            branch = res.stdout.strip() if res.returncode == 0 else "detached"
        except Exception:
            branch = "detached"

        script_worktree = os.environ.get("GIT_WORK_TREE") or "main"

        status_summary = (
            "clean (no uncommitted changes)"
            if uncommitted == 0
            else f"{uncommitted} uncommitted file(s)"
        )

        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Worktree table: split each line on whitespace, emit first 3 fields
        # (mirrors bash awk '{print "| " $1 " | " $2 " | " $3 " |"}').
        worktree_rows = []
        for line in worktree_list.splitlines():
            fields = line.split()
            f0 = fields[0] if len(fields) > 0 else ""
            f1 = fields[1] if len(fields) > 1 else ""
            f2 = fields[2] if len(fields) > 2 else ""
            worktree_rows.append(f"| {f0} | {f1} | {f2} |")
        worktree_table = "\n".join(worktree_rows)

        body = (
            f'---\n'
            f'type: git-snapshot\n'
            f'schema_version: 1\n'
            f'tags: [op/git-snapshot]\n'
            f'advisor: shared\n'
            f'captured_at: "{now_iso}"\n'
            f'ttl_seconds: {ttl}\n'
            f'branch: {branch}\n'
            f'worktree: {script_worktree}\n'
            f'---\n'
            f'\n'
            f'# Git Snapshot\n'
            f'\n'
            f'- Branch: {branch}\n'
            f'- Worktree: {script_worktree}\n'
            f'- Status: {status_summary}\n'
            f'\n'
            f'## Active worktrees\n'
            f'\n'
            f'| Path | Branch | HEAD |\n'
            f'|------|--------|------|\n'
            f'{worktree_table}\n'
        )

        snapshot.snapshot_write(cache_path, body)
        return "refreshed"
    finally:
        lock.close()
