"""test_post_commit.py — Wave 2 gate: engine post-commit subcommand + hook shim (spec 099 Task 2.3).

Includes port of hooks/test_post_commit.bats (2 cases):
  the ^ops/feedback/ filter gate for the feedback-index rebuild.
"""
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
HOOK = SCRIPTS / "hooks" / "post-commit"


def test_hook_no_subproject_refs():
    """hooks/post-commit must not reference deleted sub-project paths."""
    text = HOOK.read_text()
    assert "briefing" not in text, "hook still references deleted briefing sub-project"
    assert "feedback" not in text, "hook still references deleted feedback sub-project"
    assert "engine" in text       # delegates to the engine CLI


def test_post_commit_subcommand_exists():
    """engine post-commit --help exits 0."""
    r = subprocess.run(
        [sys.executable, "-m", "engine", "post-commit", "--help"],
        cwd=SCRIPTS, capture_output=True, text=True,
    )
    assert r.returncode == 0


# ── Port of hooks/test_post_commit.bats ───────────────────────────────────────
# Tests the ^ops/feedback/ filter gate logic (Block 2 of the old hook).
# After Wave 2 this lives in enginelib/post_commit.should_rebuild_feedback_index.


def test_feedback_filter_triggers_on_ops_feedback_files():
    """Bats port: feedback index rebuilt when commit touches ops/feedback/."""
    from enginelib.post_commit import should_rebuild_feedback_index
    assert should_rebuild_feedback_index(["ops/feedback/2026-05-22/atlas-test.md"])
    assert should_rebuild_feedback_index([
        "README.md",
        "ops/feedback/2026-05-22/other.md",
    ])


def test_feedback_filter_skips_unrelated_files():
    """Bats port: feedback index NOT rebuilt when commit does not touch ops/feedback/."""
    from enginelib.post_commit import should_rebuild_feedback_index
    assert not should_rebuild_feedback_index(["README.md"])
    assert not should_rebuild_feedback_index(["engine/scripts/foo.py", "docs/spec.md"])
    assert not should_rebuild_feedback_index([])
