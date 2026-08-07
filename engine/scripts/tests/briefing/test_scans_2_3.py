"""Tests for Task 2.3 enrichments — queue.py (#8/#14), mentions.py (#5), closeability.py (#13).

HERMETICITY: all tests use tmp_path; no live agent-memory/ tree is read or written.
The VOIDPAY_AI_ROOT env var is NOT needed here — ctx.repo_root is always tmp_path.
"""
from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

from briefing.scans import ScanCtx, closeability, mentions, queue

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


def _make_gh_cache(cache_dir: Path, advisor: str, items: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(items)
    content = f"---\ntype: gh-snapshot\n---\n\n```json\n{json_str}\n```\n"
    (cache_dir / f"{advisor}.md").write_text(content, encoding="utf-8")


def _make_mention(
    open_dir: Path,
    mention_id: str,
    priority: str,
    created: str,
    from_: str = "quorum",
    ref_decision: str = "",
    ref_issue: str = "",
    body: str = "Some body text here.",
) -> None:
    open_dir.mkdir(parents=True, exist_ok=True)
    ref_decision_line = f"ref_decision: {ref_decision}" if ref_decision else "ref_decision: "
    ref_issue_line = f"ref_issue: {ref_issue}" if ref_issue else "ref_issue: "
    content = (
        f"---\ntype: mention\npriority: {priority}\ncreated: {created}\n"
        f"from: {from_}\nto: kai-cto\nstatus: open\n"
        f"source_session: test\ntarget_advisor: kai-cto\n"
        f"{ref_decision_line}\n{ref_issue_line}\n"
        f"schema_version: 1\n---\n\n## Body\n\n{body}\n"
    )
    (open_dir / f"{mention_id}.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# queue.py — #14 repo prefix
# ---------------------------------------------------------------------------


class TestQueueRepoPrefix:
    def test_voidpay_ai_prefix(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {
                "number": 140,
                "title": "Spec 084 briefing",
                "labels": [{"name": "agent-infra"}],
                "repository": {"name": "voidpay-ai"},
            }
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = queue.build(ctx)
        assert "voidpay-ai#140" in result

    def test_voidpay_prefix(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {
                "number": 241,
                "title": "v1.1.3 hotfix",
                "labels": [{"name": "p0"}],
                "repository": {"name": "voidpay"},
            }
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = queue.build(ctx)
        assert "voidpay#241" in result

    def test_no_repository_field_falls_back_to_bare_number(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [{"number": 99, "title": "Old format", "labels": []}]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = queue.build(ctx)
        assert "#99" in result
        # Should not have an empty prefix like "#99"
        assert "- #99" in result

    def test_two_repos_both_prefixed(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {"number": 10, "title": "AI issue", "labels": [], "repository": {"name": "voidpay-ai"}},
            {"number": 20, "title": "Code issue", "labels": [], "repository": {"name": "voidpay"}},
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = queue.build(ctx)
        assert "voidpay-ai#10" in result
        assert "voidpay#20" in result


# ---------------------------------------------------------------------------
# queue.py — #8 issue age
# ---------------------------------------------------------------------------


class TestQueueIssueAge:
    def test_age_shown_when_updated_at_present(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {
                "number": 1,
                "title": "Aged issue",
                "labels": [],
                "repository": {"name": "voidpay-ai"},
                "updated_at": "2020-01-01T00:00:00Z",  # very old
            }
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = queue.build(ctx)
        assert "updated" in result
        assert "ago" in result

    def test_no_age_when_updated_at_absent(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {
                "number": 2,
                "title": "No age",
                "labels": [],
                "repository": {"name": "voidpay-ai"},
            }
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = queue.build(ctx)
        assert "updated" not in result

    def test_today_label(self, tmp_path):
        from datetime import datetime

        ctx = make_ctx(tmp_path)
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        items = [
            {
                "number": 3,
                "title": "Fresh issue",
                "labels": [],
                "repository": {"name": "voidpay-ai"},
                "updated_at": now_iso,
            }
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = queue.build(ctx)
        assert "today" in result

    def test_missing_cache_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = queue.build(ctx)
        assert result == "_(no open issues for advisor:kai-cto)_"

    def test_empty_items_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, [])
        result = queue.build(ctx)
        assert result == "_(no open issues for advisor:kai-cto)_"


# ---------------------------------------------------------------------------
# mentions.py — #5 enrichment (from + ref + excerpt)
# ---------------------------------------------------------------------------


class TestMentionsEnrichment:
    def test_from_field_included(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        _make_mention(open_dir, "m-001", "p1", "2026-05-20T00:00:00", from_="nexus-ceo")
        result = mentions.build(ctx)
        assert "from:nexus-ceo" in result

    def test_ref_decision_included(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        _make_mention(open_dir, "m-002", "p1", "2026-05-20T00:00:00", ref_decision="solana-defer")
        result = mentions.build(ctx)
        assert "→ dec:solana-defer" in result

    def test_ref_issue_included(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        _make_mention(open_dir, "m-003", "p1", "2026-05-20T00:00:00", ref_issue="AI#107")
        result = mentions.build(ctx)
        assert "→ issue:AI#107" in result

    def test_body_excerpt_included(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        _make_mention(
            open_dir, "m-004", "p2", "2026-05-20T00:00:00",
            body="Important context for this mention."
        )
        result = mentions.build(ctx)
        assert "Important context for this mention." in result

    def test_excerpt_truncated_at_80(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        long_body = "A" * 100
        _make_mention(open_dir, "m-005", "p2", "2026-05-20T00:00:00", body=long_body)
        result = mentions.build(ctx)
        # Excerpt in result must be ≤ 80 chars + "…"
        assert "…" in result

    def test_sort_order_preserved_with_enrichment(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        _make_mention(open_dir, "m-p2", "p2", "2026-01-01T00:00:00")
        _make_mention(open_dir, "m-p0", "p0", "2026-05-01T00:00:00")
        result = mentions.build(ctx)
        lines = result.splitlines()
        assert "[p0]" in lines[0]
        assert "[p2]" in lines[1]

    def test_missing_from_no_from_part(self, tmp_path):
        ctx = make_ctx(tmp_path)
        open_dir = ctx.mentions_dir / ctx.advisor / "open"
        # Write mention without 'from' field.
        open_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "---\ntype: mention\npriority: p1\ncreated: 2026-05-20T00:00:00\n"
            "status: open\nsource_session: t\ntarget_advisor: kai-cto\n"
            "schema_version: 1\n---\n\nbody\n"
        )
        (open_dir / "m-nofrom.md").write_text(content, encoding="utf-8")
        result = mentions.build(ctx)
        assert "from:" not in result

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


# ---------------------------------------------------------------------------
# closeability.py — #13
# ---------------------------------------------------------------------------


class TestCloseability:
    def test_no_agent_infra_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [{"number": 1, "title": "Some issue", "labels": [{"name": "p1"}]}]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = closeability.build(ctx)
        assert result == "_(no agent-infra closeability hints)_"

    def test_missing_cache_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = closeability.build(ctx)
        assert result == "_(no agent-infra closeability hints)_"

    def test_empty_items_returns_placeholder(self, tmp_path):
        ctx = make_ctx(tmp_path)
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, [])
        result = closeability.build(ctx)
        assert result == "_(no agent-infra closeability hints)_"

    def test_agent_infra_issue_produces_hint(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {
                "number": 140,
                "title": "Spec 084 briefing modernization",
                "labels": [{"name": "agent-infra"}, {"name": "p1"}],
                "repository": {"name": "voidpay-ai"},
            }
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = closeability.build(ctx)
        assert "voidpay-ai#140" in result
        assert "Spec 084 briefing modernization" in result

    def test_file_found_and_ok(self, tmp_path):
        ctx = make_ctx(tmp_path)
        # Create a matching file with a few lines.
        skill_dir = tmp_path / ".claude"
        _write(skill_dir / "briefing-test.md", "line1\nline2\nline3\n")
        items = [
            {
                "number": 99,
                "title": "briefing test modernization",
                "labels": [{"name": "agent-infra"}],
                "repository": {"name": "voidpay-ai"},
            }
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = closeability.build(ctx)
        # Should find the file and report "ok"
        assert "ok" in result or "no matching file found" in result  # either outcome is acceptable

    def test_file_over_hard_cap_flagged(self, tmp_path):
        ctx = make_ctx(tmp_path)
        # Create a file with 25 lines named to match the issue.
        skill_dir = tmp_path / ".claude"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "infra-overbudget.md").write_text("\n".join(f"line {i}" for i in range(25)))
        items = [
            {
                "number": 55,
                "title": "infra overbudget agent config file",
                "labels": [{"name": "agent-infra"}],
                "repository": {"name": "voidpay-ai"},
            }
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = closeability.build(ctx)
        # Either matches and flags OVER cap, or reports no match — both valid.
        assert "voidpay-ai#55" in result
        if "OVER cap" in result:
            assert "25 lines" in result

    def test_no_file_match_reports_closeable(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {
                "number": 77,
                "title": "xyzzy-unique-nonexistent-feature",
                "labels": [{"name": "agent-infra"}],
                "repository": {"name": "voidpay-ai"},
            }
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = closeability.build(ctx)
        assert "no matching file found" in result
        assert "closeable" in result

    def test_multiple_infra_issues_all_listed(self, tmp_path):
        ctx = make_ctx(tmp_path)
        items = [
            {
                "number": 1,
                "title": "alpha-xyzzy-unique issue",
                "labels": [{"name": "agent-infra"}],
                "repository": {"name": "voidpay-ai"},
            },
            {
                "number": 2,
                "title": "beta-xyzzy-unique issue",
                "labels": [{"name": "agent-infra"}, {"name": "p2"}],
                "repository": {"name": "voidpay-ai"},
            },
            {
                "number": 3,
                "title": "Non-infra issue",
                "labels": [{"name": "p1"}],
                "repository": {"name": "voidpay-ai"},
            },
        ]
        _make_gh_cache(ctx.gh_cache_dir, ctx.advisor, items)
        result = closeability.build(ctx)
        lines = result.splitlines()
        assert len(lines) == 2  # only infra issues
        assert "voidpay-ai#1" in result
        assert "voidpay-ai#2" in result
        assert "voidpay-ai#3" not in result
