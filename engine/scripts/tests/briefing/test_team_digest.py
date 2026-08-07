"""test_team_digest.py — tests for briefing.team_digest (spec 084 AC9/AC11)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from briefing.team_digest import (
    _briefing_status,
    _last_session,
    _p0_count,
    _queue_count,
    build_team_md,
    write_team_md,
)

# Local render fixture — the digest is registry-driven in production, so rendering
# tests inject an explicit roster instead of importing a hardcoded module constant.
_ADVISORS = ("nexus-ceo", "kai-cto", "shade-ciso", "spark-cmo", "quorum")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gh_cache(cache_dir: Path, advisor: str, items: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(items)
    content = f"---\ntype: gh-snapshot\n---\n\n```json\n{json_str}\n```\n"
    (cache_dir / f"{advisor}.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# _briefing_status
# ---------------------------------------------------------------------------

class TestDefaultAdvisorsRegistry:
    """#47: _default_advisors derives from the .claude/agents registry, never a
    hardcoded VoidPay tuple."""

    def test_derives_hired_roster_not_hardcoded(self, tmp_path):
        from briefing import team_digest
        agents = tmp_path / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "sage-cto.md").write_text("---\n---\n")
        (agents / "iris.md").write_text("---\n---\n")
        (agents / "forge-chro.md").write_text("---\n---\n")  # META, excluded
        result = team_digest._default_advisors(tmp_path)
        assert set(result) == {"iris", "sage-cto"}
        assert "kai-cto" not in result  # no VoidPay fallthrough

    def test_empty_registry_yields_empty(self, tmp_path):
        from briefing import team_digest
        assert team_digest._default_advisors(tmp_path) == ()


class TestBriefingStatus:
    def test_missing(self, tmp_path):
        assert _briefing_status(tmp_path / "nonexistent.md") == "missing"

    def test_recent(self, tmp_path):
        f = tmp_path / "kai-cto.md"
        f.write_text("content", encoding="utf-8")
        # mtime = now → content changed less than a day ago
        assert _briefing_status(f) == "unchanged (<1d)"

    def test_unchanged_for_days(self, tmp_path):
        """#14: elapsed time since last content change, not a staleness verdict —
        build-and-compare means an old mtime can still be perfectly accurate."""
        f = tmp_path / "kai-cto.md"
        f.write_text("content", encoding="utf-8")
        # Backdate mtime by 3 days.
        three_days_ago = f.stat().st_mtime - 3 * 86400
        os.utime(f, (three_days_ago, three_days_ago))
        result = _briefing_status(f)
        assert result.startswith("unchanged")
        assert "3d" in result


# ---------------------------------------------------------------------------
# _queue_count / _p0_count
# ---------------------------------------------------------------------------

class TestQueueAndP0:
    def test_queue_count_no_cache(self, monkeypatch, tmp_path):
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path)
        assert _queue_count("kai-cto") == 0

    def test_queue_count_with_items(self, monkeypatch, tmp_path):
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path)
        items = [
            {"number": 1, "title": "Fix foo", "labels": [{"name": "p1"}]},
            {"number": 2, "title": "Fix bar", "labels": [{"name": "p2"}]},
        ]
        _make_gh_cache(tmp_path, "kai-cto", items)
        assert _queue_count("kai-cto") == 2

    def test_p0_count_filters_correctly(self, monkeypatch, tmp_path):
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path)
        items = [
            {"number": 1, "title": "Blocker", "labels": [{"name": "p0"}]},
            {"number": 2, "title": "Normal", "labels": [{"name": "p1"}]},
            {"number": 3, "title": "Also p0", "labels": [{"name": "p0"}, {"name": "bug"}]},
        ]
        _make_gh_cache(tmp_path, "kai-cto", items)
        assert _p0_count("kai-cto") == 2

    def test_p0_count_no_p0(self, monkeypatch, tmp_path):
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path)
        items = [{"number": 1, "title": "Foo", "labels": [{"name": "p2"}]}]
        _make_gh_cache(tmp_path, "kai-cto", items)
        assert _p0_count("kai-cto") == 0


# ---------------------------------------------------------------------------
# _last_session
# ---------------------------------------------------------------------------

class TestLastSession:
    def test_no_sessions_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: tmp_path / "missing")
        assert _last_session("kai-cto") == "—"

    def test_no_matching_sessions(self, monkeypatch, tmp_path):
        sess = tmp_path / "sessions"
        sess.mkdir()
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: sess)
        # Only nexus-ceo sessions, not kai-cto.
        (sess / "2026-05-20-nexus-ceo-sprint.md").touch()
        assert _last_session("kai-cto") == "—"

    def test_returns_most_recent_slug(self, monkeypatch, tmp_path):
        sess = tmp_path / "sessions"
        sess.mkdir()
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: sess)
        (sess / "2026-05-19-kai-cto-old-work.md").touch()
        (sess / "2026-05-21-kai-cto-new-work.md").touch()
        result = _last_session("kai-cto")
        assert result == "new-work"

    def test_slug_truncated_at_40(self, monkeypatch, tmp_path):
        sess = tmp_path / "sessions"
        sess.mkdir()
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: sess)
        long_slug = "a" * 50
        (sess / f"2026-05-21-kai-cto-{long_slug}.md").touch()
        result = _last_session("kai-cto")
        assert len(result) <= 40


# ---------------------------------------------------------------------------
# build_team_md / write_team_md
# ---------------------------------------------------------------------------

class TestBuildTeamMd:
    def test_renders_5_lines_for_all_advisors(self, monkeypatch, tmp_path):
        monkeypatch.setattr("briefing.team_digest.briefings_dir", lambda: tmp_path / "briefings")
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path / "gh-cache")
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: tmp_path / "sessions")
        content = build_team_md(_ADVISORS)
        # One data row per advisor.
        data_rows = [
            line for line in content.splitlines()
            if line.startswith("|") and "advisor" not in line and "---" not in line and ":---" not in line
        ]
        assert len(data_rows) == 5

    def test_each_canonical_advisor_present(self, monkeypatch, tmp_path):
        monkeypatch.setattr("briefing.team_digest.briefings_dir", lambda: tmp_path / "briefings")
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path / "gh-cache")
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: tmp_path / "sessions")
        content = build_team_md(_ADVISORS)
        for adv in _ADVISORS:
            assert adv in content

    def test_header_present(self, monkeypatch, tmp_path):
        monkeypatch.setattr("briefing.team_digest.briefings_dir", lambda: tmp_path / "briefings")
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path / "gh-cache")
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: tmp_path / "sessions")
        content = build_team_md()
        assert "# Team digest" in content
        assert "AUTO-GENERATED" in content

    def test_write_team_md_creates_file(self, monkeypatch, tmp_path):
        bf = tmp_path / "briefings"
        bf.mkdir()
        monkeypatch.setattr("briefing.team_digest.briefings_dir", lambda: bf)
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path / "gh-cache")
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: tmp_path / "sessions")
        out = write_team_md()
        assert out == bf / "_team.md"
        assert out.is_file()

    def test_token_budget_under_500(self, monkeypatch, tmp_path):
        """_team.md content should stay ~≤500 tokens (2000 chars @ 4chars/token)."""
        monkeypatch.setattr("briefing.team_digest.briefings_dir", lambda: tmp_path / "briefings")
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path / "gh-cache")
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: tmp_path / "sessions")
        content = build_team_md(_ADVISORS)
        # Header + 5 rows should stay well within 500 tokens.
        estimated_tokens = len(content) // 4
        assert estimated_tokens < 500, (
            f"_team.md too large: ~{estimated_tokens} tokens (content={len(content)} chars)"
        )

    def test_quorum_savings_vs_full_briefings(self, monkeypatch, tmp_path):
        """_team.md must be ≥60% smaller than 5 full briefings combined (AC11)."""
        bf = tmp_path / "briefings"
        bf.mkdir()
        monkeypatch.setattr("briefing.team_digest.briefings_dir", lambda: bf)
        monkeypatch.setattr("briefing.team_digest.gh_cache_dir", lambda: tmp_path / "gh-cache")
        monkeypatch.setattr("briefing.team_digest.sessions_dir", lambda: tmp_path / "sessions")

        # Simulate 5 briefings of 2000 chars each (realistic minimum).
        total_briefing_chars = 0
        for adv in _ADVISORS:
            fake = bf / f"{adv}.md"
            fake_content = f"# Briefing — {adv}\n" + ("x" * 2000)
            fake.write_text(fake_content, encoding="utf-8")
            total_briefing_chars += len(fake_content)

        digest_content = build_team_md(_ADVISORS)
        digest_chars = len(digest_content)

        savings_pct = 1.0 - digest_chars / total_briefing_chars
        assert savings_pct >= 0.60, (
            f"Digest only saves {savings_pct:.0%} vs full briefings "
            f"(need ≥60%); digest={digest_chars} chars, full={total_briefing_chars} chars"
        )
