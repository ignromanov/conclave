"""tests/cmd/test_file_handoff.py — integration tests for `engine file handoff`.

Hermetic: uses ai_root fixture (DATA+CODE tree + env vars). Ports all 6 bats
cases from engine/scripts/tests/file-handoff.bats.

STALE-BATS NOTE: file-handoff.bats asserts the OLD filename pattern {date}-{slug}.md
(e.g. 2026-04-22-release-narrative.md). The script has written {date}-{from}-{slug}.md
since 2026-05-19. These tests assert the CORRECT name: {date}-{from}-{slug}.md.
"""
from __future__ import annotations

from pathlib import Path

from enginelib.paths import handoffs_dir
from tests.cmd.helpers import run_engine

_DATE = "2026-04-22"


def _run_handoff(body: Path, *, frm: str = "kai-cto", to: str = "spark-cmo",
                 slug: str = "release-narrative", title: str = "Release narrative",
                 priority: str = "p1", **kwargs) -> object:
    args = [
        "file", "handoff",
        "--from", frm,
        "--to", to,
        "--date", _DATE,
        "--priority", priority,
        "--title", title,
        "--slug", slug,
        "--body-file", str(body),
    ]
    for k, v in kwargs.items():
        args += [f"--{k.replace('_', '-')}", str(v)]
    return run_engine(*args)


# 1. Creates ops/handoffs/{date}-{from}-{slug}.md, exit 0
#    STALE-BATS FIX: bats assert 2026-04-22-release-narrative.md (no from-token).
#    Correct name is 2026-04-22-kai-cto-release-narrative.md.
def test_creates_handoff_file(seed_advisors, tmp_path):
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_handoff(body)
    assert r.returncode == 0
    assert (handoffs_dir() / f"{_DATE}-kai-cto-release-narrative.md").is_file()


# 2. Pattern A header present in output file
#    STALE-BATS FIX: bats check 2026-04-22-t.md; correct is 2026-04-22-kai-cto-t.md.
def test_pattern_a_header(seed_advisors, tmp_path):
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_handoff(body, frm="kai-cto", to="spark-cmo", slug="t", title="Test")
    assert r.returncode == 0
    f = handoffs_dir() / f"{_DATE}-kai-cto-t.md"
    assert f.is_file()
    content = f.read_text()
    assert "# Handoff: Test" in content
    assert "> **From**: kai-cto | **To**: spark-cmo | **Date**: 2026-04-22 | **Priority**: p1" in content


# 3. --policy renders line in output
def test_policy_renders(seed_advisors, tmp_path):
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_handoff(body, frm="kai-cto", to="nexus-ceo", slug="t", title="Test",
                     policy="references/release-policy.md")
    assert r.returncode == 0
    f = handoffs_dir() / f"{_DATE}-kai-cto-t.md"
    content = f.read_text()
    assert "Policy" in content
    assert "release-policy" in content


# 4. --gh-issue renders line in output
def test_gh_issue_renders(seed_advisors, tmp_path):
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_handoff(body, frm="kai-cto", to="nexus-ceo", slug="t", title="Test",
                     gh_issue="AI#58")
    assert r.returncode == 0
    f = handoffs_dir() / f"{_DATE}-kai-cto-t.md"
    content = f.read_text()
    assert "GH Issue" in content
    assert "AI#58" in content


# 5. No frontmatter — narrative convention (first line is not "---")
def test_no_frontmatter(seed_advisors, tmp_path):
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_handoff(body, frm="kai-cto", to="nexus-ceo", slug="t", title="Test")
    assert r.returncode == 0
    f = handoffs_dir() / f"{_DATE}-kai-cto-t.md"
    first_line = f.read_text().splitlines()[0]
    assert first_line != "---"


# 6. Required args enforced — missing most args → exit != 0, "required" in stderr
def test_required_args_enforced(seed_advisors, tmp_path):
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    r = run_engine("file", "handoff", "--from", "kai-cto")
    assert r.returncode != 0
    assert "required" in r.stderr
