"""tests/cmd/test_skill_adapter.py — `engine skill adapter` (spec 112 T4)."""
from __future__ import annotations

from enginelib import paths
from tests.cmd.helpers import run_engine

_ARGS = (
    "--stages", "implement,verify",
    "--tiers", "work",
    "--task-types", "dev",
    "--binding", "required",
    "--last-reviewed", "2026-08-09",
    "--rationale", "reached for whenever an engine test needs a fixture rethought",
)


def _seed_skill(skill: str) -> None:
    d = paths.skills_dir() / skill
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")


def test_writes_into_the_advisors_own_protocols_home(ai_root):
    _seed_skill("pytest-advanced")
    r = run_engine("skill", "adapter", "--advisor", "sage-cto", "--skill", "pytest-advanced", *_ARGS)
    assert r.returncode == 0, r.stdout + r.stderr

    target = paths.advisor_skill_dir("sage-cto") / "protocols" / "pytest-advanced.md"
    assert target.is_file(), f"adapter not at {target}"
    body = target.read_text()
    assert "external_skill: pytest-advanced" in body
    assert "stages: [implement, verify]" in body
    # never a team. prefix — operator directive 2026-07-27
    assert "/team." not in str(target)


def test_phantom_skill_writes_no_adapter(ai_root):
    r = run_engine("skill", "adapter", "--advisor", "sage-cto", "--skill", "not-real", *_ARGS)
    assert r.returncode == 3
    assert "phantom" in r.stderr
    assert not (paths.advisor_skill_dir("sage-cto") / "protocols").exists()


def test_invalid_axis_is_a_different_exit_code(ai_root):
    _seed_skill("pytest-advanced")
    bad = list(_ARGS)
    bad[bad.index("--stages") + 1] = "implement,deploy"
    r = run_engine("skill", "adapter", "--advisor", "sage-cto", "--skill", "pytest-advanced", *bad)
    assert r.returncode == 2
    assert "unknown" in r.stderr


def test_dry_run_writes_nothing(ai_root):
    _seed_skill("pytest-advanced")
    r = run_engine(
        "skill", "adapter", "--advisor", "sage-cto", "--skill", "pytest-advanced", *_ARGS, "--dry-run"
    )
    assert r.returncode == 0
    assert "would write" in r.stdout
    assert not (paths.advisor_skill_dir("sage-cto") / "protocols").exists()
