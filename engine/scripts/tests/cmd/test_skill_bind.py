"""tests/cmd/test_skill_bind.py — `engine skill bind` across both agent homes (spec 112 T3)."""
from __future__ import annotations

from pathlib import Path

from enginelib import paths
from tests.cmd.helpers import run_engine

_DEF = """---
name: {name}
description: >-
  test def
tools: Read, Grep
model: sonnet
---

body
"""


def _seed(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"{name}.md"
    p.write_text(_DEF.format(name=name), encoding="utf-8")
    return p


def _seed_skill(skill: str) -> None:
    d = paths.skills_dir() / skill
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")


def test_binds_into_a_plugin_shipped_executor_def(ai_root):
    target = _seed(paths.plugin_agents_dir(), "exec-techne-skills")
    _seed_skill("pytest-advanced")

    r = run_engine("skill", "bind", "--agent", "exec-techne-skills", "--skill", "pytest-advanced")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skills: [pytest-advanced]" in target.read_text()


def test_binds_into_a_project_side_advisor_def(ai_root):
    """The two homes are different repositories; a resolver that knew only one would pass
    every executor test and fail on the first advisor."""
    target = _seed(paths.project_agents_dir(), "sage-cto")
    _seed_skill("vitest")

    r = run_engine("skill", "bind", "--agent", "sage-cto", "--skill", "vitest")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skills: [vitest]" in target.read_text()


def test_unknown_agent_names_both_places_it_looked(ai_root):
    r = run_engine("skill", "bind", "--agent", "nobody", "--skill", "vitest")
    assert r.returncode == 2
    assert "agents" in r.stderr and r.stderr.count("\n") >= 2


def test_phantom_skill_is_refused_and_writes_nothing(ai_root):
    target = _seed(paths.plugin_agents_dir(), "exec-techne-skills")
    before = target.read_text()

    r = run_engine("skill", "bind", "--agent", "exec-techne-skills", "--skill", "not-a-real-skill")
    assert r.returncode == 3
    assert "phantom" in r.stderr
    assert target.read_text() == before, "a refused bind must not touch the file"


def test_dry_run_writes_nothing(ai_root):
    target = _seed(paths.plugin_agents_dir(), "exec-techne-skills")
    _seed_skill("pytest-advanced")
    before = target.read_text()

    r = run_engine(
        "skill", "bind", "--agent", "exec-techne-skills", "--skill", "pytest-advanced", "--dry-run"
    )
    assert r.returncode == 0
    assert "would write" in r.stdout
    assert target.read_text() == before


def test_binding_twice_is_idempotent_through_the_cli(ai_root):
    target = _seed(paths.plugin_agents_dir(), "exec-techne-skills")
    _seed_skill("pytest-advanced")

    run_engine("skill", "bind", "--agent", "exec-techne-skills", "--skill", "pytest-advanced")
    once = target.read_text()
    r = run_engine("skill", "bind", "--agent", "exec-techne-skills", "--skill", "pytest-advanced")

    assert r.returncode == 0
    assert "already bound" in r.stdout
    assert target.read_text() == once
