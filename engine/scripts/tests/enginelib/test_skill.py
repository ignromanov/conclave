"""tests/enginelib/test_skill.py — tests for enginelib.skill.verify."""
from __future__ import annotations

from enginelib import skill


def test_project_local_hit(tmp_path, monkeypatch):
    """verify() returns the local SKILL.md when the skill exists in skills_dir()."""
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
