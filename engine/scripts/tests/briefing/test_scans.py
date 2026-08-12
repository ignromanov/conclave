"""Tests for briefing.scans.* — all 7 scan modules."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Live-instance tests: gated by the `live_instance` marker, whose conftest fixture points
# CONCLAVE_AI_ROOT at CONCLAVE_LIVE_INSTANCE_ROOT for marked tests only. The old form gated
# on CONCLAVE_AI_ROOT itself — a variable the hermetic conftest clears — so it was asking
# whether hermeticity had been switched off, and the answer was always no (GH#105).
_NEEDS_INSTANCE = pytest.mark.live_instance

from briefing.scans import (
    ScanCtx,
    decisions,
    identity,
    mentions,
    p0,
    project_state,
    queue,
    sessions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(tmp_path: Path, advisor: str = "kai-cto") -> ScanCtx:
    """Build a ScanCtx wired to tmp_path fixture dirs."""
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


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_missing_file_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = identity.build(ctx)
        assert result == "_(personality.md not yet written — run /conclave:forge to seed it)_"

    def test_placeholder_names_a_command_that_exists(self, tmp_path):
        """Pinning the exact string proves it is stable, not that it is useful — it
        pinned `/team.forge` just as firmly for as long as no such command existed.
        Resolve whatever command the placeholder names against the shipped set, so
        the assertion survives a reword and fails on a phantom.

        The commands dir is derived from this file's own location rather than
        engine_root(): inside a worktree CONCLAVE_ENGINE_ROOT still points at the
        main checkout (#86), so a shipped-asset lookup would read the wrong tree.
        """
        import re

        result = identity.build(make_ctx(tmp_path))
        named = re.findall(r"/conclave:([a-z-]+)", result)
        assert named, f"placeholder names no /conclave: command: {result}"
        commands = Path(__file__).resolve().parents[4] / "commands"
        missing = [n for n in named if not (commands / f"{n}.md").is_file()]
        assert not missing, f"placeholder names non-existent command(s) {missing} in {commands}"

    def test_no_frontmatter_returns_body(self, tmp_path):
        ctx = make_ctx(tmp_path)
        _write(ctx.personality_path, "Hello, I am Kai.\n\nSecond paragraph.\n")
        result = identity.build(ctx)
        assert "Hello, I am Kai." in result
        assert "Second paragraph." in result

    def test_strips_frontmatter_block(self, tmp_path):
        ctx = make_ctx(tmp_path)
        content = "---\ntitle: Kai\ntype: identity\n---\n\nI am the CTO advisor.\n"
        _write(ctx.personality_path, content)
        result = identity.build(ctx)
        assert "I am the CTO advisor." in result
        assert "---" not in result
        assert "title:" not in result

    def test_trims_leading_blank_lines(self, tmp_path):
        ctx = make_ctx(tmp_path)
        content = "---\ntitle: X\n---\n\n\n\nFirst real line.\n"
        _write(ctx.personality_path, content)
        result = identity.build(ctx)
        assert result.startswith("First real line.")

    @_NEEDS_INSTANCE
    def test_real_personality(self, live_ctx):
        """Integration: the live instance's own advisor renders a real persona."""
        result = identity.build(live_ctx)
        assert "_(personality.md not yet written" not in result, (
            f"{live_ctx.advisor}'s persona resolved to {live_ctx.personality_path}, "
            "which does not exist"
        )
        assert len(result) > 10


# ---------------------------------------------------------------------------
# project_state
# ---------------------------------------------------------------------------

class TestProjectState:
    def test_missing_file_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = project_state.build(ctx)
        assert result == "_(progress-summary.md missing)_"

    def test_skips_top_level_heading(self, tmp_path):
        ctx = make_ctx(tmp_path)
        _write(ctx.progress_path, "# Progress Summary\n\n**Phase**: P1\n")
        result = project_state.build(ctx)
        assert "# Progress Summary" not in result
        assert "**Phase**: P1" in result

    def test_skips_blockquote_lines(self, tmp_path):
        ctx = make_ctx(tmp_path)
        _write(ctx.progress_path, "> meta note\n\n**Phase**: P1\n")
        result = project_state.build(ctx)
        assert "> meta note" not in result
        assert "**Phase**: P1" in result

    def test_head_20_truncation(self, tmp_path):
        ctx = make_ctx(tmp_path)
        lines = [f"Line {i}" for i in range(30)]
        _write(ctx.progress_path, "\n".join(lines))
        result = project_state.build(ctx)
        result_lines = result.splitlines()
        assert len(result_lines) == 20
        assert result_lines[0] == "Line 0"
        assert result_lines[-1] == "Line 19"

    def test_trims_leading_blanks(self, tmp_path):
        ctx = make_ctx(tmp_path)
        _write(ctx.progress_path, "\n\n\nActual content\n")
        result = project_state.build(ctx)
        assert result.startswith("Actual content")

    @_NEEDS_INSTANCE
    def test_real_progress_summary(self, live_ctx):
        """Integration: project_state honours its contract on whichever branch the live tree
        lands in. progress-summary.md is optional per-instance DATA, so 'absent' is a
        legitimate state — asserting only the present branch is what made this skip."""
        result = project_state.build(live_ctx)
        if live_ctx.progress_path.is_file():
            assert result != "_(progress-summary.md missing)_"
            assert len(result.splitlines()) <= 20
        else:
            assert result == "_(progress-summary.md missing)_"


# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------

class TestDecisions:
    def test_missing_dir_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = decisions.build(ctx)
        assert result == "_(no decisions recorded yet)_"

    def test_empty_dir_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.decisions_dir.mkdir(parents=True)
        result = decisions.build(ctx)
        assert result == "_(no decisions recorded yet)_"

    def test_returns_top_5_sorted_desc(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.decisions_dir.mkdir(parents=True)
        # Create 7 files — only 5 newest (lexicographic) should appear.
        for i in range(7):
            f = ctx.decisions_dir / f"2026-0{i+1}-01-kai-cto-dec.md"
            f.write_text("---\ntype: decision\n---\nbody\n")
        result = decisions.build(ctx)
        lines = result.splitlines()
        assert len(lines) == 5
        # Newest first (sort -r).
        assert "2026-07-01" in lines[0]
        assert "2026-03-01" in lines[-1]

    def test_link_format(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.decisions_dir.mkdir(parents=True)
        f = ctx.decisions_dir / "2026-05-01-kai-cto-test-decision.md"
        f.write_text("body\n")
        result = decisions.build(ctx)
        assert "- [2026-05-01-kai-cto-test-decision](decisions/2026-05-01-kai-cto-test-decision.md)" in result

    def test_only_matches_advisor(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.decisions_dir.mkdir(parents=True)
        (ctx.decisions_dir / "2026-05-01-kai-cto-dec.md").write_text("x")
        (ctx.decisions_dir / "2026-05-01-nexus-ceo-dec.md").write_text("x")
        result = decisions.build(ctx)
        assert "kai-cto" in result
        assert "nexus-ceo" not in result

    @_NEEDS_INSTANCE
    def test_real_decisions(self, live_ctx):
        """Integration: real decisions dir returns links."""
        result = decisions.build(live_ctx)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# queue
# ---------------------------------------------------------------------------

def _make_gh_cache(cache_dir: Path, advisor: str, items: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(items)
    content = f"---\ntype: gh-snapshot\n---\n\n```json\n{json_str}\n```\n"
    (cache_dir / f"{advisor}.md").write_text(content, encoding="utf-8")


class TestQueue:
    def test_missing_cache_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = queue.build(ctx)
        assert "_(no open issues for advisor:kai-cto)_" == result

    def test_formats_rows_as_list(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {"number": 42, "title": "Fix the thing", "labels": [{"name": "p1"}]},
            {"number": 43, "title": "Another issue", "labels": []},
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = queue.build(ctx)
        assert "- #42 | Fix the thing | p1" in result
        assert "- #43 | Another issue | " in result

    def test_empty_items_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, [])
        result = queue.build(ctx)
        assert "_(no open issues for advisor:kai-cto)_" == result

    @_NEEDS_INSTANCE
    def test_real_queue(self, live_ctx):
        """Integration: gh-cache is optional — an instance may have no GitHub at all — so
        assert the contract of whichever branch the live tree lands in, rather than skipping
        and reporting nothing."""
        result = queue.build(live_ctx)
        placeholder = f"_(no open issues for advisor:{live_ctx.advisor})_"
        snapshot = live_ctx.gh_cache_dir / f"{live_ctx.advisor}.md"
        if not snapshot.is_file():
            assert result == placeholder
            return
        # Expectation is keyed on the snapshot's CONTENTS, not its existence: a cached
        # snapshot holding zero items is a legitimate state (an advisor with nothing open,
        # or — as measured on this instance — one whose GH label was dropped by a rename,
        # GH#111). Keying on the file alone made this test redden on the instance's label
        # hygiene rather than on the scan's contract.
        raw = snapshot.read_text(encoding="utf-8")
        items = json.loads(raw.split("```json", 1)[1].split("```", 1)[0])
        if items:
            assert placeholder not in result
            # Queue rows carry a repo prefix (e.g. "conclave#140") per enrichment #14.
            assert result.startswith("- ")
        else:
            assert result == placeholder


# ---------------------------------------------------------------------------
# p0
# ---------------------------------------------------------------------------

class TestP0:
    def test_no_p0_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [{"number": 1, "title": "Some issue", "labels": [{"name": "p1"}]}]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = p0.build(ctx)
        assert result == "_(no global p0 blockers)_"

    def test_filters_p0_rows(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {"number": 1, "title": "Blocker", "labels": [{"name": "p0"}, {"name": "advisor:kai"}]},
            {"number": 2, "title": "Nice to have", "labels": [{"name": "p2"}]},
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = p0.build(ctx)
        assert "- #1 | Blocker |" in result
        assert "#2" not in result

    def test_missing_cache_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = p0.build(ctx)
        assert result == "_(no global p0 blockers)_"

    @_NEEDS_INSTANCE
    def test_real_p0(self, live_ctx):
        """Integration: p0 renders either real blockers or the documented placeholder —
        both of which name p0."""
        result = p0.build(live_ctx)
        assert isinstance(result, str)
        assert "p0" in result


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------

class TestSessions:
    def test_missing_dir_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = sessions.build(ctx)
        assert result == "_(no prior sessions recorded)_"

    def test_empty_dir_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.sessions_dir.mkdir(parents=True)
        result = sessions.build(ctx)
        assert result == "_(no prior sessions recorded)_"

    def test_returns_top_3_sorted_desc(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.sessions_dir.mkdir(parents=True)
        for i in range(5):
            f = ctx.sessions_dir / f"2026-0{i+1}-01-kai-cto-sess.md"
            f.write_text("body\n")
        result = sessions.build(ctx)
        lines = result.splitlines()
        assert len(lines) == 3
        assert "2026-05-01" in lines[0]
        assert "2026-03-01" in lines[-1]

    def test_link_format(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.sessions_dir.mkdir(parents=True)
        f = ctx.sessions_dir / "2026-05-20-kai-cto-test-session.md"
        f.write_text("body\n")
        result = sessions.build(ctx)
        assert "- [2026-05-20-kai-cto-test-session](sessions/2026-05-20-kai-cto-test-session.md)" in result

    def test_only_matches_advisor(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.sessions_dir.mkdir(parents=True)
        (ctx.sessions_dir / "2026-05-01-kai-cto-s.md").write_text("x")
        (ctx.sessions_dir / "2026-05-01-nexus-ceo-s.md").write_text("x")
        result = sessions.build(ctx)
        assert "kai-cto" in result
        assert "nexus-ceo" not in result

    @_NEEDS_INSTANCE
    def test_real_sessions(self, live_ctx):
        """Integration: real sessions dir returns a non-empty render."""
        result = sessions.build(live_ctx)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# mentions
# ---------------------------------------------------------------------------

def _make_mention(open_dir: Path, mention_id: str, priority: str, created: str) -> None:
    open_dir.mkdir(parents=True, exist_ok=True)
    content = (
        f"---\ntype: mention\npriority: {priority}\ncreated: {created}\n"
        f"status: open\nsource_session: test\ntarget_advisor: kai-cto\n"
        f"schema_version: 1\n---\n\nbody\n"
    )
    (open_dir / f"{mention_id}.md").write_text(content, encoding="utf-8")


class TestMentions:
    def test_missing_dir_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = mentions.build(ctx)
        assert result == "_(no open mentions)_"

    def test_empty_dir_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        open_dir.mkdir(parents=True)
        result = mentions.build(ctx)
        assert result == "_(no open mentions)_"

    def test_sorted_priority_then_date_desc(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        _make_mention(open_dir, "m-p2-old", "p2", "2026-01-01T00:00:00")
        _make_mention(open_dir, "m-p0-new", "p0", "2026-05-01T00:00:00")
        _make_mention(open_dir, "m-p1-mid", "p1", "2026-03-01T00:00:00")
        _make_mention(open_dir, "m-p2-new", "p2", "2026-05-20T00:00:00")
        result = mentions.build(ctx)
        lines = result.splitlines()
        # p0 first
        assert "[p0]" in lines[0]
        # p1 second
        assert "[p1]" in lines[1]
        # p2 newest before p2 oldest
        assert "m-p2-new" in lines[2]
        assert "m-p2-old" in lines[3]

    def test_link_format(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        _make_mention(open_dir, "2026-05-20-q-to-kai-thing", "p1", "2026-05-20T00:00:00")
        result = mentions.build(ctx)
        expected_link = "mentions/kai-cto/open/2026-05-20-q-to-kai-thing.md"
        assert expected_link in result
        assert "[p1]" in result
        assert "2026-05-20T00:00:00" in result

    def test_default_priority_p2(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        open_dir.mkdir(parents=True)
        # Write mention without priority field.
        content = "---\ntype: mention\nstatus: open\ncreated: 2026-05-01T00:00:00\nsource_session: t\ntarget_advisor: kai-cto\nschema_version: 1\n---\nbody\n"
        (open_dir / "m-noprio.md").write_text(content, encoding="utf-8")
        result = mentions.build(ctx)
        assert "[p2]" in result

    @_NEEDS_INSTANCE
    def test_real_mentions(self, live_ctx):
        """Integration: real mentions dir returns a non-empty render."""
        result = mentions.build(live_ctx)
        assert isinstance(result, str)
        assert len(result) > 0
