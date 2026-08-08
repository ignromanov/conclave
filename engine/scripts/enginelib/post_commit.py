"""enginelib/post_commit.py — core git post-commit logic (spec 099).

I/O-free: no print(), no argparse, no sys.exit.
Imports briefing and feedback packages directly — no uv run --project shelling out.
"""
from __future__ import annotations

import subprocess


def get_changed_files() -> list[str]:
    """Return files changed in HEAD via git diff-tree (canonical post-commit approach)."""
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", "HEAD"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def should_rebuild_feedback_index(changed_files: list[str]) -> bool:
    """Return True if any changed file is under ops/feedback/ (Block 2 gate)."""
    return any(f.startswith("ops/feedback/") for f in changed_files)


def run_briefing_regen(changed_files: list[str]) -> int:
    """Parse advisor names from changed files and regen their briefings.

    Returns number of failures (0 = all OK).
    """
    from briefing.regen import advisors_from_commit_diff, regen_advisors
    from enginelib.advisors import canonical_advisors
    diff_output = "\n".join(changed_files)
    advisors = advisors_from_commit_diff(diff_output, canonical_advisors())
    if not advisors:
        return 0
    return regen_advisors(advisors)


def run_feedback_index() -> int:
    """Rebuild the feedback JSONL index. Returns exit code (0 = OK)."""
    from feedback.feedback_index import main as feedback_index_main
    return feedback_index_main([])


def post_commit() -> int:
    """Run all post-commit tasks. Returns 0 on success, 1 on any failure (non-fatal)."""
    changed = get_changed_files()
    if not changed:
        return 0

    exit_code = 0

    # Block 1: briefing regen for advisors touched in commit
    try:
        failures = run_briefing_regen(changed)
        if failures:
            exit_code = 1
    except Exception:
        exit_code = 1

    # Block 2: feedback index rebuild when ops/feedback/ is touched
    if should_rebuild_feedback_index(changed):
        try:
            rc = run_feedback_index()
            if rc != 0:
                exit_code = 1
        except Exception:
            exit_code = 1

    return exit_code
