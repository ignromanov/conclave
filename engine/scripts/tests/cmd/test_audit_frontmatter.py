"""test_audit_frontmatter.py — the 084 §4 schema check, finally reachable from a command.

`validate_file`/`validate_tree` shipped with pydantic models and 24 tests and ZERO
production callers: §A4 named three consumers (briefing-build, validator, backfill) and
none was built. This is the audit adapter that makes the check runnable, and these are the
two properties an adapter can get wrong without any test noticing.
"""
from __future__ import annotations

from pathlib import Path

from enginelib.audit import frontmatter as fm_audit


def _record(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_it_reports_a_record_its_type_rejects(tmp_path):
    _record(tmp_path, "ops/specs/bad.md",
            "---\ntype: spec\nstatus: proposed\n---\nno owner, no id\n")

    findings = fm_audit.run(tmp_path)

    assert findings.crit, "a spec missing required fields must be CRIT"
    assert any("bad.md" in line for line in findings.crit), findings.crit


def test_the_path_it_reports_is_relative_to_the_root_it_was_given(tmp_path):
    """A wall of absolute temp paths is unreadable, and hides which tree was walked."""
    _record(tmp_path, "ops/specs/bad.md", "---\ntype: spec\n---\nbody\n")

    findings = fm_audit.run(tmp_path)

    assert any(line.startswith("ops/specs/bad.md") for line in findings.crit), findings.crit


def test_an_empty_root_is_clean_rather_than_an_error(tmp_path):
    """The control: a clean result must mean "nothing wrong", not "nothing looked at".

    This is the half that made the first wiring of this audit report `0 CRIT, 0 WARN`
    against a tree holding 463 findings — it was handed `project_root()` (the CODE
    checkout) where the records live in DATA. A clean bill of health from a directory
    that holds no records at all is indistinguishable from a real one, Which root the
    COMMAND walks is pinned separately, below — these module-level tests are handed a
    root and so can say nothing about that choice.
    """
    findings = fm_audit.run(tmp_path)

    assert findings.crit == []
    assert findings.warn == []


def test_the_command_walks_the_data_root_not_the_code_checkout(tmp_path, monkeypatch):
    """`engine audit frontmatter` must resolve DATA, where the records live.

    Wired to `project_root()` first, this audit reported `0 CRIT, 0 WARN` against an
    instance holding 463 findings: project_root() is the CODE checkout and holds no
    records at all, so the walk came back clean because it was empty. Nothing in the
    suite could see that — every other test in this file is HANDED its root — and it
    surfaced only because the number to compare against had already been measured.

    The two roots point at different trees here and only the DATA one is seeded, so a
    run that reports nothing is a run that walked the other one.
    """
    import argparse

    from engine.cmd import audit as audit_cmd

    data_root, code_root = tmp_path / "data", tmp_path / "code"
    (code_root / "ops" / "specs").mkdir(parents=True)
    _record(data_root, "ops/specs/bad.md",
            "---\ntype: spec\nstatus: proposed\n---\nbody\n")

    monkeypatch.setattr("enginelib.paths.repo_root", lambda: data_root)
    monkeypatch.setattr("enginelib.paths.project_root", lambda: code_root)

    rc = audit_cmd._frontmatter(argparse.Namespace())

    assert rc != 0, "a record its own type rejects must make the audit exit non-zero"
