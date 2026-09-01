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
    # Every handoff carries a resolvable reference or a recorded reason (#55). Tests that
    # are not about the reference get a valid one so they keep measuring what they measured.
    if "gh_issue" not in kwargs and "no_issue" not in kwargs:
        args += ["--gh-issue", "AI#12"]
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


# --- #55: a handoff must reference something a later reader can resolve ---

def test_handoff_without_a_reference_is_refused(seed_advisors, tmp_path):
    """Handoffs have no terminal state: resume-scan ranks by mtime and never learns the
    work shipped, so an exhausted one resurfaces forever (two observed at 1374h and
    1226h, both tracking PRs merged in July). A resolvable reference is the cheapest
    thing that lets a reader answer "is this still live?" without reading the whole file.
    """
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_handoff(body, slug="noref", title="Test", no_issue="")
    assert r.returncode == 1
    assert "--no-issue" in r.stderr
    assert not (handoffs_dir() / f"{_DATE}-kai-cto-noref.md").exists()


def test_unresolvable_reference_is_refused(seed_advisors, tmp_path):
    """A bare number names nothing. That is not hypothetical: `AI#113` was written meaning
    spec 113 while GH#113 was an unrelated merged PR about executors."""
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    for bad in ("113", "see the PR", "spec 093", "#"):
        r = _run_handoff(body, slug="bad", title="Test", gh_issue=bad)
        assert r.returncode == 1, f"accepted unresolvable reference {bad!r}"
        assert "resolvable" in r.stderr


def test_resolvable_reference_shapes_are_accepted(seed_advisors, tmp_path):
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    for i, ref in enumerate(("#12", "AI#12", "ignromanov/conclave#12",
                             "https://github.com/ignromanov/conclave/pull/166")):
        r = _run_handoff(body, slug=f"ok{i}", title="Test", gh_issue=ref)
        assert r.returncode == 0, f"{ref}: {r.stderr}"
        assert ref in (handoffs_dir() / f"{_DATE}-kai-cto-ok{i}.md").read_text()


def test_no_issue_records_the_reason_in_the_document(seed_advisors, tmp_path):
    """The escape hatch has to leave a trace, or it is indistinguishable from the omission
    it replaces — the same reason verify_waiver: is a field rather than a convention."""
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_handoff(body, slug="spike", title="Test",
                     no_issue="exploratory spike, nothing filed yet")
    assert r.returncode == 0, r.stderr
    content = (handoffs_dir() / f"{_DATE}-kai-cto-spike.md").read_text()
    assert "exploratory spike, nothing filed yet" in content


def test_both_reference_and_reason_is_refused(seed_advisors, tmp_path):
    seed_advisors("kai-cto", "spark-cmo", "nexus-ceo")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_handoff(body, slug="both", title="Test", gh_issue="AI#12", no_issue="also this")
    assert r.returncode == 1
    assert "not both" in r.stderr
