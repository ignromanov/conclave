"""Tests for render.check_token_cap and identity.py eager-file preference."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Skip live-instance tests when no instance root is available (D3).
_NEEDS_INSTANCE = pytest.mark.skipif(
    not (os.environ.get("CONCLAVE_AI_ROOT") or os.environ.get("VOIDPAY_AI_ROOT")),
    reason="needs live instance root",
)

from briefing.render import _CHARS_PER_TOKEN, _TOKEN_CAP, check_token_cap
from briefing.scans import ScanCtx, identity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


# ---------------------------------------------------------------------------
# check_token_cap
# ---------------------------------------------------------------------------

class TestCheckTokenCap:
    def test_no_warning_under_cap(self, tmp_path, capsys):
        """Small briefing body does not emit a warning."""
        values = {
            "advisor": "kai-cto",
            "generated_at": "2026-05-21T00:00:00+0000",
            "who_i_am": "Short identity text.",
            "project_state": "Phase P1.",
        }
        check_token_cap(values)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_warning_emitted_over_cap(self, tmp_path, capsys):
        """Briefing body exceeding cap emits a WARNING to stderr."""
        # Build a value large enough to exceed the cap.
        # floor(n // 4) > _TOKEN_CAP requires n >= (_TOKEN_CAP + 1) * _CHARS_PER_TOKEN.
        over_limit_text = "x" * ((_TOKEN_CAP + 1) * _CHARS_PER_TOKEN)
        values = {
            "advisor": "kai-cto",
            "generated_at": "2026-05-21T00:00:00+0000",
            "who_i_am": over_limit_text,
        }
        check_token_cap(values)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "token" in captured.err.lower()
        assert str(_TOKEN_CAP) in captured.err

    def test_excludes_metadata_keys(self, tmp_path, capsys):
        """advisor and generated_at are excluded from token count."""
        # If metadata were counted, this would be over the cap.
        big_metadata = "y" * (_TOKEN_CAP * _CHARS_PER_TOKEN + 1)
        values = {
            "advisor": big_metadata,
            "generated_at": big_metadata,
            "who_i_am": "small",
        }
        check_token_cap(values)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_exactly_at_cap_no_warning(self, tmp_path, capsys):
        """Exactly at the cap (not over) does not warn."""
        at_cap_text = "z" * (_TOKEN_CAP * _CHARS_PER_TOKEN)
        values = {
            "advisor": "nexus-ceo",
            "generated_at": "2026-05-21T00:00:00+0000",
            "who_i_am": at_cap_text,
        }
        check_token_cap(values)
        captured = capsys.readouterr()
        assert captured.err == ""


# ---------------------------------------------------------------------------
# identity.build — eager file preference
# ---------------------------------------------------------------------------

class TestIdentityEagerPreference:
    def test_prefers_eager_over_full(self, tmp_path):
        """When both personality-eager.md and personality.md exist, eager wins."""
        ctx = make_ctx(tmp_path)
        _write(ctx.personality_path, "Full personality text.\n")
        eager_path = ctx.personality_path.parent / "personality-eager.md"
        _write(eager_path, "Eager personality text.\n")

        result = identity.build(ctx)
        assert "Eager personality text." in result
        assert "Full personality text." not in result

    def test_falls_back_to_full_when_eager_absent(self, tmp_path):
        """When only personality.md exists, it is used."""
        ctx = make_ctx(tmp_path)
        _write(ctx.personality_path, "Full personality text.\n")

        result = identity.build(ctx)
        assert "Full personality text." in result

    def test_placeholder_when_neither_exists(self, tmp_path):
        """When neither file exists, returns placeholder."""
        ctx = make_ctx(tmp_path)
        result = identity.build(ctx)
        assert "_(personality.md not yet written" in result

    def test_eager_strips_frontmatter(self, tmp_path):
        """Frontmatter is stripped from personality-eager.md."""
        ctx = make_ctx(tmp_path)
        eager_path = ctx.personality_path.parent / "personality-eager.md"
        _write(
            eager_path,
            "---\nname: Kai\ntype: identity\n---\n\nEager body content.\n",
        )
        result = identity.build(ctx)
        assert "Eager body content." in result
        assert "type: identity" not in result

    @_NEEDS_INSTANCE
    def test_real_kai_cto_eager(self):
        """Integration: real kai-cto personality-eager.md produces non-placeholder output."""
        from briefing.paths import (
            decisions_dir,
            gh_cache_dir,
            mentions_dir,
            repo_root,
            sessions_dir,
        )
        eager_path = (
            repo_root()
            / ".claude"
            / "skills"
            / "team.kai-cto"
            / "memory"
            / "personality-eager.md"
        )
        if not eager_path.is_file():
            pytest.skip("personality-eager.md not found for kai-cto")
        ctx = ScanCtx(
            advisor="kai-cto",
            short_name="kai",
            repo_root=repo_root(),
            decisions_dir=decisions_dir(),
            sessions_dir=sessions_dir(),
            mentions_dir=mentions_dir(),
            gh_cache_dir=gh_cache_dir(),
            personality_path=repo_root()
            / ".claude"
            / "skills"
            / "team.kai-cto"
            / "memory"
            / "personality.md",
            progress_path=repo_root() / "progress-summary.md",
        )
        result = identity.build(ctx)
        assert "_(personality.md not yet written" not in result
        assert len(result) > 10
