"""Tests for render.check_token_cap and identity.py eager-file preference."""
from __future__ import annotations

from pathlib import Path

import pytest

# Live-instance tests: gated by the `live_instance` marker, whose conftest fixture points
# CONCLAVE_AI_ROOT at CONCLAVE_LIVE_INSTANCE_ROOT for marked tests only. The old form gated
# on CONCLAVE_AI_ROOT itself — a variable the hermetic conftest clears — so it was asking
# whether hermeticity had been switched off, and the answer was always no (GH#105).
_NEEDS_INSTANCE = pytest.mark.live_instance

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
        project_root=tmp_path,
        plans_dir=tmp_path / ".claude" / "plans",
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

class TestIdentitySource:
    """Was TestIdentityEagerPreference. Two of its cases asserted that
    `personality-eager.md` wins over `personality.md` — and passed, while nothing in
    the engine has ever written a `personality-eager.md` and no such file exists in any
    instance. The preferred branch was therefore dead in production and green in the
    suite: a test true regardless of whether the feature was reachable. The dead
    preference is removed (spec 116 F1/F3); whether 084's eager/archival split should be
    built for real is a live question filed separately."""

    def test_reads_personality_md(self, tmp_path):
        """personality.md is the source."""
        ctx = make_ctx(tmp_path)
        _write(ctx.personality_path, "Full personality text.\n")

        result = identity.build(ctx)
        assert "Full personality text." in result

    def test_placeholder_when_neither_exists(self, tmp_path):
        """When neither file exists, returns placeholder."""
        ctx = make_ctx(tmp_path)
        result = identity.build(ctx)
        assert "_(personality.md not yet written" in result

    def test_strips_frontmatter(self, tmp_path):
        """Frontmatter is stripped from personality.md."""
        ctx = make_ctx(tmp_path)
        _write(
            ctx.personality_path,
            "---\nname: Kai\ntype: identity\n---\n\nPersona body content.\n",
        )
        result = identity.build(ctx)
        assert "Persona body content." in result
        assert "type: identity" not in result

    @_NEEDS_INSTANCE
    def test_real_persona_renders(self, live_ctx):
        """Integration: identity renders the live advisor's persona, not a placeholder.

        The eager branch is covered synthetically above. It gets no live coverage on
        purpose: no advisor in this project has ever had a personality-eager.md, so the
        old form of this test — skip unless one exists — could only ever report nothing."""
        result = identity.build(live_ctx)
        assert "_(personality.md not yet written" not in result
        assert len(result) > 10
