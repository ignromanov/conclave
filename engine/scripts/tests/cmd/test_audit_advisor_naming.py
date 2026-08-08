"""`engine audit advisor-naming` — report ids that predate the naming standard.

The validator refuses at the two doors an id can ENTER through (create, rename).
Ids already on disk were never asked, so a report is the only way to find them —
and a report, not a refusal, because the fix for a live advisor is a migration
with memory attached, not a rejected command.
"""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine


def _agents(tmp: Path, *ids: str) -> Path:
    d = tmp / ".claude" / "agents"
    d.mkdir(parents=True, exist_ok=True)
    for i in ids:
        (d / f"{i}.md").write_text(f"---\nname: {i}\n---\n", encoding="utf-8")
    return d


def _audit(tmp: Path):
    return run_engine(
        "audit", "advisor-naming",
        env={"CONCLAVE_AI_ROOT": str(tmp), "CONCLAVE_RUN_LOG_DIR": f"{tmp}-rl"},
    )


def test_clean_roster_passes(tmp_path):
    _agents(tmp_path, "sage-cto", "vera-cto", "atlas-cro")
    r = _audit(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_reports_every_non_conforming_id(tmp_path):
    _agents(tmp_path, "sage-cto", "engineering-data", "testx", "growth-monetization")
    r = _audit(tmp_path)
    assert r.returncode != 0, r.stdout
    for offender in ("engineering-data", "testx", "growth-monetization"):
        assert offender in r.stdout, r.stdout
    assert "sage-cto" not in r.stdout, "a conforming id must not be reported"


def test_executors_are_not_advisors(tmp_path):
    """exec-* has its own gate with its own vocabulary; auditing it here would
    report every executor as a broken advisor."""
    _agents(tmp_path, "sage-cto", "exec-atlas-dev", "exec-iris-test")
    r = _audit(tmp_path)
    assert r.returncode == 0, r.stdout


def test_the_report_names_the_allowed_roles(tmp_path):
    _agents(tmp_path, "privacy-trust")
    r = _audit(tmp_path)
    assert "cdpo" in r.stdout, r.stdout


def test_the_legacy_team_prefix_is_not_part_of_the_id(tmp_path):
    """`team.<id>.md` is the pre-103 filename convention; the id is what follows.

    Measured on the VoidPay instance, whose five advisors all conform and were
    all reported as broken because the audit judged the filename."""
    _agents(tmp_path, "team.kai-cto", "team.nexus-ceo", "team.quorum")
    r = _audit(tmp_path)
    assert "kai-cto" not in r.stdout, r.stdout
    assert "nexus-ceo" not in r.stdout, r.stdout
    assert "quorum" in r.stdout, "the one id that really lacks a role must survive"
    assert r.returncode != 0, r.stdout


def test_the_legacy_dot_executor_form_is_still_an_executor(tmp_path):
    """Executors were `exec.<name>-<role>` before the hyphen standard. Skipping
    only `exec-` reported six of VoidPay's executors as broken advisors."""
    _agents(tmp_path, "sage-cto", "exec.scout", "exec.atlas-dev", "exec.judge")
    r = _audit(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_dangling_symlink_is_not_an_advisor(tmp_path):
    """The project's `.claude/agents/` is a symlink layer over the DATA tree.
    Retiring an advisor deletes the target and can leave the link behind, and a
    glob sees the link — so the audit reported a file that does not exist as a
    non-conforming advisor and told the operator to migrate its memory."""
    d = _agents(tmp_path, "sage-cto")
    (d / "testx.md").symlink_to(tmp_path / "gone" / "testx.md")
    r = _audit(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_an_empty_roster_is_clean(tmp_path):
    _agents(tmp_path)
    r = _audit(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
