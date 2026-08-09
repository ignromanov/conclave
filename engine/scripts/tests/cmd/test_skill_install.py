"""tests/cmd/test_skill_install.py — `engine skill install` policy surface (spec 112 T2).

No test here downloads anything. The refusal paths never reach a subprocess, and the allowed
path is exercised with --dry-run; asserting on a real install would be asserting on GitHub.
"""
from __future__ import annotations

from enginelib import paths
from tests.cmd.helpers import run_engine


def _allowlist_file():
    return paths.forge_references_dir() / "skill-sources.md"


def test_offlist_package_is_refused(ai_root):
    r = run_engine("skill", "install", "stranger/repo@skill")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "refused" in r.stderr


def test_refusal_names_the_manual_command(ai_root):
    """A refusal hands the decision back; it must not read as 'nothing to do here'."""
    r = run_engine("skill", "install", "stranger/repo@skill")
    assert "skills add stranger/repo@skill -g -y" in r.stderr
    assert "skill-sources.md" in r.stderr


def test_malformed_package_is_a_different_exit_code(ai_root):
    """2 = you asked wrong, 3 = you asked for something not permitted. Callers branch on it."""
    r = run_engine("skill", "install", "not-a-package")
    assert r.returncode == 2
    assert "malformed" in r.stderr


def test_allowed_package_dry_run_prints_and_installs_nothing(ai_root):
    r = run_engine("skill", "install", "obra/superpowers@brainstorming", "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "would install: skills add obra/superpowers@brainstorming -g -y" in r.stdout


def test_an_emptied_allowlist_refuses_a_previously_allowed_package(ai_root):
    """The gate is the file, not the code path.

    Planted defect, inverted: empty the list and a package that just passed must stop passing.
    Without this, a bug that ignored the file entirely would leave every other test green.
    """
    before = run_engine("skill", "install", "obra/superpowers@brainstorming", "--dry-run")
    assert before.returncode == 0

    f = _allowlist_file()
    f.write_text("## Allowed sources\n\n## Notes\n- emptied by a test\n", encoding="utf-8")

    after = run_engine("skill", "install", "obra/superpowers@brainstorming", "--dry-run")
    assert after.returncode == 3, "an empty allowlist must refuse everything"


def test_missing_allowlist_refuses_rather_than_defaulting_open(ai_root):
    _allowlist_file().unlink()
    r = run_engine("skill", "install", "obra/superpowers@brainstorming", "--dry-run")
    assert r.returncode == 3
    assert "refusing everything" in r.stderr
