"""tests/cmd/test_skill_verify.py — integration tests for `engine skill verify`.

Ports the 2 cases from engine/scripts/tests/verify-skill.test.sh.
"""
from __future__ import annotations

from tests.cmd.helpers import run_engine


def test_known_skill_prints_path(seed_advisors):
    """engine skill verify team.start → exit 0 AND stdout ends with team.start/SKILL.md."""
    seed_advisors("start")
    r = run_engine("skill", "verify", "team.start")
    assert r.returncode == 0
    assert r.stdout.strip().endswith("team.start/SKILL.md")


def test_phantom_skill_empty_stdout(ai_root):
    """engine skill verify <phantom> → exit 0 AND stdout is empty."""
    r = run_engine("skill", "verify", "team.fake-advisor-does-not-exist")
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_batch_all_present_exits_zero(seed_advisors):
    """Multiple names, all resolvable → exit 0, one OK line per name, no PHANTOM."""
    seed_advisors("start")
    r = run_engine("skill", "verify", "team.start", "team.start")
    assert r.returncode == 0
    assert "PHANTOM" not in r.stdout
    assert r.stdout.count("OK\t") == 2
    assert "team.start/SKILL.md" in r.stdout


def test_batch_reports_phantom_and_exits_nonzero(seed_advisors):
    """Batch with a phantom → exit 1, a PHANTOM line for the missing skill, OK for the real one."""
    seed_advisors("start")
    r = run_engine("skill", "verify", "team.start", "team.fake-does-not-exist")
    assert r.returncode == 1
    assert "PHANTOM\tteam.fake-does-not-exist" in r.stdout
    assert "OK\tteam.start\t" in r.stdout
