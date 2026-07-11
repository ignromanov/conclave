"""Tests for briefing.render — template substitution + atomic write."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from briefing.render import _hot_section, _substitute
from briefing.scans import ScanCtx

# Skip live-instance tests when no instance root is available (D3).
_NEEDS_INSTANCE = pytest.mark.skipif(
    not (os.environ.get("CONCLAVE_AI_ROOT") or os.environ.get("VOIDPAY_AI_ROOT")),
    reason="needs live instance root",
)


# ---------------------------------------------------------------------------
# Helpers
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


def _make_gh_cache(cache_dir: Path, advisor: str, items: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(items)
    content = f"---\ntype: gh-snapshot\n---\n\n```json\n{json_str}\n```\n"
    (cache_dir / f"{advisor}.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# _substitute
# ---------------------------------------------------------------------------

class TestSubstitute:
    def test_simple_replacement(self):
        template = "Hello {{name}}!"
        result = _substitute(template, {"name": "Kai"})
        assert result == "Hello Kai!"

    def test_multiline_value(self):
        template = "## Section\n\n{{content}}\n\n## End"
        value = "Line one\nLine two\nLine three"
        result = _substitute(template, {"content": value})
        assert "Line one\nLine two\nLine three" in result

    def test_unknown_placeholder_preserved(self):
        template = "{{known}} and {{unknown}}"
        result = _substitute(template, {"known": "X"})
        assert "X and {{unknown}}" == result

    def test_multiple_placeholders(self):
        template = "{{a}} + {{b}} = {{c}}"
        result = _substitute(template, {"a": "1", "b": "2", "c": "3"})
        assert result == "1 + 2 = 3"

    def test_placeholder_with_newlines_in_value(self):
        """Verify newlines inside a value don't break surrounding text."""
        template = "before\n{{val}}\nafter"
        result = _substitute(template, {"val": "line1\nline2"})
        assert result == "before\nline1\nline2\nafter"


# ---------------------------------------------------------------------------
# _hot_section
# ---------------------------------------------------------------------------

class TestHotSection:
    def test_missing_hot_md(self, tmp_path):
        result = _hot_section(tmp_path / "nonexistent.md")
        assert "not initialized" in result

    def test_includes_now_section(self, tmp_path):
        hot = tmp_path / "hot.md"
        hot.write_text(
            "## Now\n\nDoing X.\n\n## Background\n\nOld info.\n\n## Watch\n\nThing Y.\n",
            encoding="utf-8",
        )
        result = _hot_section(hot)
        assert "## Now" in result
        assert "Doing X." in result
        assert "## Watch" in result
        assert "Thing Y." in result
        # Background is excluded.
        assert "## Background" not in result
        assert "Old info." not in result

    def test_includes_recent_decisions_section(self, tmp_path):
        hot = tmp_path / "hot.md"
        hot.write_text(
            "## Recent decisions\n\n- dec A\n\n## Other\n\nignored\n",
            encoding="utf-8",
        )
        result = _hot_section(hot)
        assert "## Recent decisions" in result
        assert "dec A" in result
        assert "ignored" not in result

    def test_excludes_open_threads(self, tmp_path):
        hot = tmp_path / "hot.md"
        hot.write_text(
            "## Open threads\n\nThread stuff\n\n## Now\n\nCurrent.\n",
            encoding="utf-8",
        )
        result = _hot_section(hot)
        assert "Thread stuff" not in result
        assert "Current." in result

    def test_empty_hot_md(self, tmp_path):
        hot = tmp_path / "hot.md"
        hot.write_text("", encoding="utf-8")
        result = _hot_section(hot)
        assert result == ""


# ---------------------------------------------------------------------------
# render.build — full integration
# ---------------------------------------------------------------------------

class TestRenderBuild:
    @pytest.fixture(autouse=True)
    def _fake_instance_root(self, tmp_path, monkeypatch):
        """Set CONCLAVE_AI_ROOT=tmp_path so hot_md_path() resolves without a live instance."""
        import briefing.paths as _paths
        monkeypatch.setattr(_paths, "_REPO_ROOT_CACHE", None)
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))

    def test_produces_output_file(self, tmp_path):
        """render.build() writes a file at the given path."""
        from briefing.render import build as render_build
        ctx = make_ctx(tmp_path)
        out = tmp_path / "briefings" / "kai-cto.md"
        render_build(ctx, out)
        assert out.is_file()

    def test_advisor_placeholder_substituted(self, tmp_path):
        from briefing.render import build as render_build
        ctx = make_ctx(tmp_path)
        out = tmp_path / "briefings" / "kai-cto.md"
        render_build(ctx, out)
        content = out.read_text(encoding="utf-8")
        # Template has <!-- advisor: {{advisor}} --> — should be substituted.
        assert "kai-cto" in content
        # No raw {{advisor}} placeholder remaining.
        assert "{{advisor}}" not in content

    def test_no_unresolved_placeholders(self, tmp_path):
        from briefing.render import build as render_build
        ctx = make_ctx(tmp_path)
        out = tmp_path / "briefings" / "kai-cto.md"
        render_build(ctx, out)
        content = out.read_text(encoding="utf-8")
        import re
        unresolved = re.findall(r"\{\{[a-zA-Z0-9_]+\}\}", content)
        assert unresolved == [], f"Unresolved placeholders: {unresolved}"

    def test_placeholders_fallback_to_defaults(self, tmp_path):
        """With no data on disk, all sections use placeholder strings."""
        from briefing.render import build as render_build
        ctx = make_ctx(tmp_path)
        out = tmp_path / "briefings" / "kai-cto.md"
        render_build(ctx, out)
        content = out.read_text(encoding="utf-8")
        assert "_(personality.md not yet written" in content
        assert "_(progress-summary.md missing)_" in content
        assert "_(no decisions recorded yet)_" in content
        assert "_(no prior sessions recorded)_" in content
        assert "_(no open mentions)_" in content

    def test_multiline_personality_in_output(self, tmp_path):
        """Multi-line personality body renders without truncation."""
        from briefing.render import build as render_build
        ctx = make_ctx(tmp_path)
        ctx.personality_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.personality_path.write_text(
            "---\ntitle: Kai\n---\n\nLine A\nLine B\nLine C\n", encoding="utf-8"
        )
        out = tmp_path / "briefings" / "kai-cto.md"
        render_build(ctx, out)
        content = out.read_text(encoding="utf-8")
        assert "Line A" in content
        assert "Line B" in content
        assert "Line C" in content

    def test_hot_md_reference_appended(self, tmp_path):
        """hot.md path reference footer appended (AC8 — content not embedded)."""
        from briefing.render import build as render_build
        ctx = make_ctx(tmp_path)
        out = tmp_path / "briefings" / "kai-cto.md"
        render_build(ctx, out)
        content = out.read_text(encoding="utf-8")
        # Reference line present, raw section block absent.
        assert "Live context" in content
        assert "hot.md" in content
        assert "## Live (hot.md)" not in content

    def test_hot_md_content_not_embedded(self, tmp_path):
        """hot.md sections (Now/Recent decisions/Watch) must not appear inline (AC8)."""
        from briefing.render import build as render_build
        ctx = make_ctx(tmp_path)
        # Write a hot.md with recognisable content.
        hot = tmp_path / "agent-memory" / "hot.md"
        hot.parent.mkdir(parents=True, exist_ok=True)
        hot.write_text(
            "## Now\n\nSENTINEL_NOW\n\n## Recent decisions\n\nSENTINEL_DEC\n",
            encoding="utf-8",
        )
        out = tmp_path / "briefings" / "kai-cto.md"
        render_build(ctx, out)
        content = out.read_text(encoding="utf-8")
        assert "SENTINEL_NOW" not in content
        assert "SENTINEL_DEC" not in content

    def test_atomic_write_replaces_existing(self, tmp_path):
        """Calling render.build twice overwrites the file atomically."""
        from briefing.render import build as render_build
        ctx = make_ctx(tmp_path)
        out = tmp_path / "briefings" / "kai-cto.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("stale content", encoding="utf-8")
        render_build(ctx, out)
        content = out.read_text(encoding="utf-8")
        assert "stale content" not in content


# ---------------------------------------------------------------------------
# Live-instance integration (skipped when no instance root is configured)
# ---------------------------------------------------------------------------

@_NEEDS_INSTANCE
def test_real_kai_cto_integration():
    """Integration: render produces a briefing for kai-cto using real data."""
    from briefing.paths import (
        decisions_dir,
        gh_cache_dir,
        mentions_dir,
        repo_root,
        sessions_dir,
    )
    from briefing.render import build as render_build

    root = repo_root()
    ctx = ScanCtx(
        advisor="kai-cto",
        short_name="kai",
        repo_root=root,
        decisions_dir=decisions_dir(),
        sessions_dir=sessions_dir(),
        mentions_dir=mentions_dir(),
        gh_cache_dir=gh_cache_dir(),
        personality_path=root / ".claude" / "skills" / "team.kai-cto" / "memory" / "personality.md",
        progress_path=root / "progress-summary.md",
    )
    # Write to a temp location — don't touch real briefings.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "kai-cto.md"
        render_build(ctx, out)
        content = out.read_text(encoding="utf-8")

    assert "# Briefing — kai-cto" in content
    # AC8: hot.md reference present, content not embedded.
    assert "Live context" in content
    assert "## Live (hot.md)" not in content
    # No raw placeholders remaining.
    import re
    unresolved = re.findall(r"\{\{[a-zA-Z0-9_]+\}\}", content)
    assert unresolved == []
    # Should have real data (not all placeholders).
    assert "_(personality.md not yet written" not in content
