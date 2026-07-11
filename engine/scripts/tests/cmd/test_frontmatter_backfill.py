"""tests/cmd/test_frontmatter_backfill.py — adapter smokes for `engine frontmatter backfill`.

Package internals are covered by tests/briefing/test_backfill_cli.py and
tests/briefing/test_backfill.py. These tests verify only the adapter wiring.
"""
from __future__ import annotations

from tests.cmd.helpers import run_engine


def test_backfill_no_flags_exits_zero(tmp_path):
    """engine frontmatter backfill (no flags) → exit 0 (dry-run default; empty tree is safe)."""
    r = run_engine("frontmatter", "backfill", env={"CONCLAVE_AI_ROOT": str(tmp_path)})
    assert r.returncode == 0


def test_backfill_apply_without_confirm_exits_nonzero(tmp_path):
    """engine frontmatter backfill --apply (no --confirm) → exit 1 AND stderr has safety message."""
    r = run_engine("frontmatter", "backfill", "--apply", env={"CONCLAVE_AI_ROOT": str(tmp_path)})
    assert r.returncode == 1
    assert "--apply requires --confirm" in r.stderr


def test_backfill_dry_run_exits_zero(tmp_path):
    """engine frontmatter backfill --dry-run → exit 0."""
    r = run_engine("frontmatter", "backfill", "--dry-run", env={"CONCLAVE_AI_ROOT": str(tmp_path)})
    assert r.returncode == 0
