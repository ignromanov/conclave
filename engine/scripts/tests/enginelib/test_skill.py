"""tests/enginelib/test_skill.py — tests for enginelib.skill.verify."""
from __future__ import annotations

from enginelib import skill


def test_engine_skills_hit(tmp_path, monkeypatch):
    """verify() returns the SKILL.md shipped in the engine's own skills_dir().

    Named `test_project_local_hit` until #74: `skills_dir()` is `engine_root()/skills`,
    the ENGINE's skills, not the consumer project's. The old name is the same conflation
    that made verify() report a consumer's own skills as phantoms.
    """
    engine_root = tmp_path / "engine"
    skills = engine_root / "skills"
    (skills / "find-skills").mkdir(parents=True)
    (skills / "find-skills" / "SKILL.md").write_text("# find-skills\n")
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine_root))
    monkeypatch.setenv("CONCLAVE_GLOBAL_SKILLS_DIR", str(tmp_path / "global"))
    monkeypatch.setenv("CLAUDE_PLUGINS_CACHE", str(tmp_path / "cache"))

    result = skill.verify("find-skills")

    assert result == skills / "find-skills" / "SKILL.md"


def test_namespaced_cache_hit_prefers_matching_plugin(tmp_path, monkeypatch):
    """verify() with plugin:skill prefers the cache entry whose plugin dir == namespace."""
    engine_root = tmp_path / "engine"
    (engine_root / "skills").mkdir(parents=True)
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine_root))
    monkeypatch.setenv("CONCLAVE_GLOBAL_SKILLS_DIR", str(tmp_path / "global"))

    cache = tmp_path / "cache"
    # Non-matching plugin comes first alphabetically
    wrong = cache / "owner1" / "other-plugin" / "1.0.0" / "skills" / "brainstorming"
    wrong.mkdir(parents=True)
    (wrong / "SKILL.md").write_text("# wrong\n")
    # Matching plugin: dir name == namespace "superpowers"
    right = cache / "owner2" / "superpowers" / "1.0.0" / "skills" / "brainstorming"
    right.mkdir(parents=True)
    (right / "SKILL.md").write_text("# right\n")
    monkeypatch.setenv("CLAUDE_PLUGINS_CACHE", str(cache))

    result = skill.verify("superpowers:brainstorming")

    assert result == right / "SKILL.md"


def test_miss_returns_none(tmp_path, monkeypatch):
    """verify() returns None when the skill cannot be found anywhere."""
    engine_root = tmp_path / "engine"
    (engine_root / "skills").mkdir(parents=True)
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine_root))
    monkeypatch.setenv("CONCLAVE_GLOBAL_SKILLS_DIR", str(tmp_path / "global"))
    monkeypatch.setenv("CLAUDE_PLUGINS_CACHE", str(tmp_path / "cache"))

    result = skill.verify("definitely-nonexistent-skill-xyz")

    assert result is None


def _isolate(tmp_path, monkeypatch):
    """Point every non-project search root at an empty dir, so a hit can only be
    project-local. Returns the consumer project root."""
    engine_root = tmp_path / "engine"
    (engine_root / "skills").mkdir(parents=True)
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine_root))
    monkeypatch.setenv("CONCLAVE_GLOBAL_SKILLS_DIR", str(tmp_path / "global"))
    monkeypatch.setenv("CLAUDE_PLUGINS_CACHE", str(tmp_path / "cache"))
    project = tmp_path / "consumer"
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    return project


def test_consumer_claude_skills_hit(tmp_path, monkeypatch):
    """#74: a skill in <project>/.claude/skills/ resolves instead of reporting PHANTOM."""
    project = _isolate(tmp_path, monkeypatch)
    skill_md = project / ".claude" / "skills" / "invoice-chase" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("# invoice-chase\n")

    assert skill.verify("invoice-chase") == skill_md


def test_consumer_agents_skills_hit(tmp_path, monkeypatch):
    """#74: the .agents/skills/ root is searched too — the vault instance used it."""
    project = _isolate(tmp_path, monkeypatch)
    skill_md = project / ".agents" / "skills" / "linkedin-profile-optimizer" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("# linkedin-profile-optimizer\n")

    assert skill.verify("linkedin-profile-optimizer") == skill_md


def test_consumer_skill_wins_over_global(tmp_path, monkeypatch):
    """A project's own skill shadows a same-named global one — most specific wins."""
    project = _isolate(tmp_path, monkeypatch)
    local = project / ".claude" / "skills" / "price-check" / "SKILL.md"
    local.parent.mkdir(parents=True)
    local.write_text("# local\n")
    glob_md = tmp_path / "global" / "price-check" / "SKILL.md"
    glob_md.parent.mkdir(parents=True)
    glob_md.write_text("# global\n")

    assert skill.verify("price-check") == local


def test_no_project_dir_does_not_crash(tmp_path, monkeypatch):
    """With CLAUDE_PROJECT_DIR unset the project roots must degrade quietly, not raise.

    project_root() falls back to repo_root(), which raises when no DATA root is
    locatable — verify() must not turn that into a crash for engine/global callers.
    """
    engine_root = tmp_path / "engine"
    (engine_root / "skills" / "find-skills").mkdir(parents=True)
    (engine_root / "skills" / "find-skills" / "SKILL.md").write_text("# f\n")
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine_root))
    monkeypatch.setenv("CONCLAVE_GLOBAL_SKILLS_DIR", str(tmp_path / "global"))
    monkeypatch.setenv("CLAUDE_PLUGINS_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    assert skill.verify("find-skills") == engine_root / "skills" / "find-skills" / "SKILL.md"
