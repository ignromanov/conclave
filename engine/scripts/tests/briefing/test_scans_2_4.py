"""Tests for Task 2.4 enrichments:
  - scans/decisions.py: now also scans ops/decisions/ (Y-statements).
  - scans/code_repo.py: code-repo awareness (git log + newer docs/).

HERMETICITY: no test reads or writes the live agent-memory/ tree.
All fixtures are built under tmp_path.  The VOIDPAY_AI_ROOT env var
is used to isolate repo_root() calls in code_repo detection.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from briefing.scans import ScanCtx, code_repo, decisions

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_ctx(tmp_path: Path, advisor: str = "kai-cto") -> ScanCtx:
    short = advisor.split("-")[0]
    return ScanCtx(
        advisor=advisor,
        short_name=short,
        repo_root=tmp_path,
        decisions_dir=tmp_path / "agent-memory" / "advisors" / "decisions",
        sessions_dir=tmp_path / "agent-memory" / "advisors" / "sessions",
        mentions_dir=tmp_path / "agent-memory" / "advisors" / "mentions",
        gh_cache_dir=tmp_path / "agent-memory" / "gh-cache",
        personality_path=tmp_path / ".claude" / "skills" / f"team.{advisor}" / "memory" / "personality.md",
        progress_path=tmp_path / "progress-summary.md",
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _init_git_repo(repo: Path) -> None:
    """Initialise a bare-minimum git repo with one commit."""
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"],
                   check=True, capture_output=True)
    # Seed a file so there's something to commit.
    seed = repo / "README.md"
    seed.write_text("seed\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"],
                   check=True, capture_output=True)


# ---------------------------------------------------------------------------
# decisions.py — ops/decisions/ widening
# ---------------------------------------------------------------------------

class TestDecisionsOpsDir:
    def test_ops_decisions_included(self, tmp_path):
        """An ops/decisions/ file appears in the output even with no advisor files."""
        ctx = make_ctx(tmp_path)
        # No advisor decisions dir.
        ops_dec = tmp_path / "ops" / "decisions"
        ops_dec.mkdir(parents=True)
        _write(ops_dec / "2026-05-20-codec-compression-strategy.md", "body\n")

        result = decisions.build(ctx)
        assert "2026-05-20-codec-compression-strategy" in result

    def test_ops_and_advisor_decisions_merged(self, tmp_path):
        """Both sources are merged; top 5 taken from the combined pool."""
        ctx = make_ctx(tmp_path)

        # 3 advisor decisions.
        ctx.decisions_dir.mkdir(parents=True)
        for i in range(1, 4):
            _write(
                ctx.decisions_dir / f"2026-05-0{i}-kai-cto-dec.md",
                "body\n",
            )

        # 3 ops/decisions.
        ops_dec = tmp_path / "ops" / "decisions"
        ops_dec.mkdir(parents=True)
        for i in range(4, 7):
            _write(ops_dec / f"2026-05-0{i}-cross-cutting.md", "body\n")

        result = decisions.build(ctx)
        lines = result.splitlines()
        # Combined 6 unique entries → top 5 returned.
        assert len(lines) == 5
        # Newest overall is 2026-05-06 (ops entry).
        assert "2026-05-06" in lines[0]

    def test_ops_decisions_skips_meta_stems(self, tmp_path):
        """INDEX.md / README.md / template.md in ops/decisions/ are excluded."""
        ctx = make_ctx(tmp_path)
        ops_dec = tmp_path / "ops" / "decisions"
        ops_dec.mkdir(parents=True)
        _write(ops_dec / "INDEX.md", "meta\n")
        _write(ops_dec / "README.md", "meta\n")
        _write(ops_dec / "template.md", "meta\n")

        result = decisions.build(ctx)
        assert result == "_(no decisions recorded yet)_"

    def test_ops_decisions_missing_dir_falls_back_to_advisor_only(self, tmp_path):
        """When ops/decisions/ doesn't exist, advisor files still work."""
        ctx = make_ctx(tmp_path)
        ctx.decisions_dir.mkdir(parents=True)
        _write(ctx.decisions_dir / "2026-05-01-kai-cto-dec.md", "body\n")

        result = decisions.build(ctx)
        assert "2026-05-01-kai-cto-dec" in result

    def test_placeholder_when_both_dirs_empty_or_missing(self, tmp_path):
        """Placeholder returned when neither source has any files."""
        ctx = make_ctx(tmp_path)
        result = decisions.build(ctx)
        assert result == "_(no decisions recorded yet)_"

    def test_deduplication(self, tmp_path):
        """Duplicate stems across both dirs appear only once."""
        ctx = make_ctx(tmp_path)
        ctx.decisions_dir.mkdir(parents=True)
        ops_dec = tmp_path / "ops" / "decisions"
        ops_dec.mkdir(parents=True)
        # Same stem in both dirs (unlikely in practice but must be safe).
        stem = "2026-05-01-kai-cto-shared-dec"
        _write(ctx.decisions_dir / f"{stem}.md", "body\n")
        _write(ops_dec / f"{stem}.md", "body\n")

        result = decisions.build(ctx)
        lines = result.splitlines()
        assert lines.count(f"- [{stem}](decisions/{stem}.md)") == 1


# ---------------------------------------------------------------------------
# code_repo.py — code-repo awareness
# ---------------------------------------------------------------------------

class TestCodeRepoEmptyState:
    def test_placeholder_when_cwd_is_ai_root(self, tmp_path, monkeypatch):
        """Returns placeholder when cwd is the .ai/ repo itself."""
        # Build a minimal git repo at tmp_path to act as the .ai/ root.
        _init_git_repo(tmp_path)
        ctx = make_ctx(tmp_path)

        # cwd == ai_root → must return placeholder.
        monkeypatch.chdir(tmp_path)
        result = code_repo.build(ctx)
        assert result == "_(no code repo in cwd — running from .ai/ or non-git directory)_"

    def test_placeholder_when_cwd_is_non_git(self, tmp_path, monkeypatch):
        """Returns placeholder when cwd is not inside any git repo."""
        # tmp_path/non_git is a plain dir, not a git repo.
        non_git = tmp_path / "non_git"
        non_git.mkdir()
        ctx = make_ctx(tmp_path)

        monkeypatch.chdir(non_git)
        result = code_repo.build(ctx)
        assert result == "_(no code repo in cwd — running from .ai/ or non-git directory)_"


class TestCodeRepoRealCase:
    def test_returns_git_log_section(self, tmp_path, monkeypatch):
        """When cwd is a code repo distinct from ai_root, git log is included."""
        ai_root = tmp_path / "ai"
        ai_root.mkdir()
        code_root = tmp_path / "code"
        _init_git_repo(code_root)

        ctx = make_ctx(ai_root)
        monkeypatch.chdir(code_root)

        result = code_repo.build(ctx)
        # Should contain the init commit from _init_git_repo.
        assert "init" in result
        assert "**Recent commits:**" in result

    def test_docs_newer_than_session_included(self, tmp_path, monkeypatch):
        """docs/ files created after the last session appear in output."""

        ai_root = tmp_path / "ai"
        ai_root.mkdir()
        code_root = tmp_path / "code"
        _init_git_repo(code_root)

        # Create a session file with an old mtime (in the past).
        ctx = make_ctx(ai_root)
        sess_dir = ctx.sessions_dir
        sess_dir.mkdir(parents=True)
        old_session = sess_dir / "2026-01-01-kai-cto-old.md"
        old_session.write_text("body\n")
        # Force mtime to epoch so anything created now is "newer".
        import os
        os.utime(old_session, (0, 0))

        # Create a docs/ file (definitely newer than epoch).
        docs_dir = code_root / "docs"
        docs_dir.mkdir()
        (docs_dir / "architecture.md").write_text("arch\n")

        monkeypatch.chdir(code_root)
        result = code_repo.build(ctx)
        assert "docs/architecture.md" in result

    def test_docs_older_than_session_excluded(self, tmp_path, monkeypatch):
        """docs/ files older than the last session are excluded."""
        import os
        import time

        ai_root = tmp_path / "ai"
        ai_root.mkdir()
        code_root = tmp_path / "code"
        _init_git_repo(code_root)

        ctx = make_ctx(ai_root)
        sess_dir = ctx.sessions_dir
        sess_dir.mkdir(parents=True)
        # Session file with mtime = far future.
        new_session = sess_dir / "2026-05-20-kai-cto-recent.md"
        new_session.write_text("body\n")
        future_ts = time.time() + 86400  # 1 day ahead
        os.utime(new_session, (future_ts, future_ts))

        # docs/ file with mtime = now (before future session).
        docs_dir = code_root / "docs"
        docs_dir.mkdir()
        (docs_dir / "old-doc.md").write_text("old\n")

        monkeypatch.chdir(code_root)
        result = code_repo.build(ctx)
        # docs/old-doc.md is older than the (future-dated) session → not shown.
        assert "old-doc.md" not in result

    def test_no_docs_dir_returns_log_only(self, tmp_path, monkeypatch):
        """When the code repo has no docs/ dir, only the git log section renders."""
        ai_root = tmp_path / "ai"
        ai_root.mkdir()
        code_root = tmp_path / "code"
        _init_git_repo(code_root)

        ctx = make_ctx(ai_root)
        monkeypatch.chdir(code_root)

        result = code_repo.build(ctx)
        assert "**Recent commits:**" in result
        assert "**docs/ changed since" not in result

    def test_docs_skip_stems_excluded(self, tmp_path, monkeypatch):
        """README.md and other meta-stems in docs/ are not reported."""
        import os

        ai_root = tmp_path / "ai"
        ai_root.mkdir()
        code_root = tmp_path / "code"
        _init_git_repo(code_root)

        ctx = make_ctx(ai_root)
        # Session at epoch so all files are "newer".
        sess_dir = ctx.sessions_dir
        sess_dir.mkdir(parents=True)
        old_session = sess_dir / "2026-01-01-kai-cto-old.md"
        old_session.write_text("body\n")
        os.utime(old_session, (0, 0))

        docs_dir = code_root / "docs"
        docs_dir.mkdir()
        (docs_dir / "README.md").write_text("read\n")
        (docs_dir / "CHANGELOG.md").write_text("change\n")
        (docs_dir / "api-reference.md").write_text("api\n")

        monkeypatch.chdir(code_root)
        result = code_repo.build(ctx)
        assert "README.md" not in result
        assert "CHANGELOG.md" not in result
        assert "api-reference.md" in result
