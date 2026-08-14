"""Unit tests for the routing-target resolver — each plants the defect its check exists to catch."""
from __future__ import annotations

from pathlib import Path

from enginelib.audit import Findings
from enginelib.audit import routing_targets as rt


def test_a_dotted_token_is_extracted_with_its_line_number():
    text = "row one\n| Meeting | team.quorum |\nrow three\n"
    assert rt.find_dotted(text) == [(2, "team.quorum")]


def test_a_workflow_token_is_extracted_whether_backticked_or_bare():
    text = "invoke `workflow.iterative-loop` now\n| Dev | workflow.dev-lifecycle |\n"
    assert rt.find_dotted(text) == [
        (1, "workflow.iterative-loop"),
        (2, "workflow.dev-lifecycle"),
    ]


def test_an_ai_root_reference_is_extracted():
    text = "check `.ai/references/compaction-triggers.md` first\n"
    assert rt.find_ai_root_refs(text) == [(1, ".ai/references/compaction-triggers.md")]


def test_a_bare_ai_root_in_prose_is_extracted():
    text = "Commits go to the `.ai/` repo.\n"
    assert rt.find_ai_root_refs(text) == [(1, ".ai/")]


def test_a_conclave_path_is_not_an_ai_root_reference():
    text = "written to `.conclave/agent-memory/hot.md`\n"
    assert rt.find_ai_root_refs(text) == []


def test_a_dotted_word_ending_in_ai_is_not_an_ai_root_reference():
    """`openai/` and `foo.ai/` must not match — the guard is the preceding-character class."""
    text = "see https://example.ai/docs and vendor/openai/client.py\n"
    assert rt.find_ai_root_refs(text) == []


def test_a_path_embedded_ai_root_with_no_trailing_slash_is_extracted():
    """`.ai` with a path segment but no trailing slash — `cd /path/to/.ai` — must be found; the
    original regex required a trailing `/` and missed exactly this shape."""
    text = "cd /path/to/.ai\n"
    assert rt.find_ai_root_refs(text) == [(1, ".ai")]


def test_a_bare_backticked_ai_root_with_no_trailing_slash_is_extracted():
    text = "open a GitHub Issue in the `.ai` repo\n"
    assert rt.find_ai_root_refs(text) == [(1, ".ai")]


def test_a_longer_extension_ending_in_ai_is_not_an_ai_root_reference():
    """`.aiff` / `.airc` must not fire — the guard is the trailing-character class, not just the
    preceding one."""
    text = "convert the .aiff file and check .airc config\n"
    assert rt.find_ai_root_refs(text) == []


def _surface(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


ROSTER = frozenset({"sage-cto", "forge-chro"})


def test_run_is_clean_when_every_target_resolves(tmp_path: Path):
    root = tmp_path / "skills"
    (root / "workflow.real").mkdir(parents=True)
    s = _surface(tmp_path, "ok.md", "invoke `workflow.real` and `team.sage-cto` and `team.done`\n")
    assert rt.run([s], [root], ROSTER) == Findings(crit=[], warn=[])


def test_run_flags_a_workflow_token_with_no_directory(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    s = _surface(tmp_path, "bad.md", "invoke `workflow.ghost` now\n")
    findings = rt.run([s], [root], ROSTER)
    assert len(findings.crit) == 1
    assert "workflow.ghost" in findings.crit[0]
    assert "bad.md:1" in findings.crit[0]


def test_run_does_not_flag_a_team_token_that_names_a_lifecycle_skill(tmp_path: Path):
    """The team.* rename debt is 28 occurrences and out of P1 scope — flagging it would make
    this phase unable to go green without doing the rename it excludes."""
    root = tmp_path / "skills"
    root.mkdir()
    s = _surface(tmp_path, "life.md", "`team.start` then `team.processing` then `team.done`\n")
    assert rt.run([s], [root], ROSTER) == Findings(crit=[], warn=[])


def test_run_flags_team_quorum_because_no_roster_entry_matches(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    s = _surface(tmp_path, "q.md", "| Meeting | Invoke team.quorum |\n")
    findings = rt.run([s], [root], ROSTER)
    assert len(findings.crit) == 1
    assert "team.quorum" in findings.crit[0]


def test_run_does_not_flag_team_quorum_when_the_roster_hired_one(tmp_path: Path):
    """An instance that hired a facilitator makes this reference correct — the rule is the roster,
    never a hardcoded verdict (GH#82)."""
    root = tmp_path / "skills"
    root.mkdir()
    s = _surface(tmp_path, "q.md", "| Meeting | Invoke team.quorum |\n")
    assert rt.run([s], [root], ROSTER | {"quorum"}, ) == Findings(crit=[], warn=[])


def test_run_flags_an_ai_root_reference(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    s = _surface(tmp_path, "ai.md", "Run git status in `/` and `.ai/`\n")
    findings = rt.run([s], [root], ROSTER)
    assert len(findings.crit) == 1
    assert ".ai/" in findings.crit[0]


def test_run_reports_every_finding_not_just_the_first(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    s = _surface(tmp_path, "many.md", "`workflow.a` and `workflow.b` and `.ai/x.md`\n")
    assert len(rt.run([s], [root], ROSTER).crit) == 3


def test_an_unreadable_surface_is_skipped_not_raised(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    assert rt.run([tmp_path / "gone.md"], [root], ROSTER) == Findings(crit=[], warn=[])
