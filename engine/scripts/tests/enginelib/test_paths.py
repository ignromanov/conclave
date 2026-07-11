from pathlib import Path

import pytest

from enginelib import paths


def _make_ai_root(tmp_path: Path) -> Path:
    root = tmp_path / ".ai"
    (root / "ops").mkdir(parents=True)
    (root / ".claude").mkdir(parents=True)
    return root


def test_repo_root_from_env(tmp_path, monkeypatch):
    root = _make_ai_root(tmp_path)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    assert paths.repo_root() == root


def test_advisors_memory_dir_absolute(tmp_path, monkeypatch):
    root = _make_ai_root(tmp_path)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    assert str(paths.advisors_memory_dir()).endswith("/agent-memory/advisors")


def test_ensure_dir_creates(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    assert not target.exists()
    paths.ensure_dir(target)
    assert target.is_dir()


def test_ensure_dir_idempotent(tmp_path):
    target = tmp_path / "a"
    paths.ensure_dir(target)
    paths.ensure_dir(target)
    assert target.is_dir()


def test_repo_root_walks_up(tmp_path, monkeypatch):
    root = _make_ai_root(tmp_path)
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    nested = root / ".claude" / "skills" / "team.forge"
    nested.mkdir(parents=True)
    assert paths.repo_root(start=nested).resolve() == root.resolve()


def test_repo_root_actionable_error_outside_tree(tmp_path, monkeypatch):
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    with pytest.raises(RuntimeError, match="unable to locate"):
        paths.repo_root(start=tmp_path)


def test_snapshot_path_invalid_cache_type(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(_make_ai_root(tmp_path)))
    with pytest.raises(ValueError):
        paths.snapshot_path_for_advisor("bogus", "nexus-ceo")


def test_feedback_dir(tmp_path, monkeypatch):
    root = _make_ai_root(tmp_path)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    assert str(paths.feedback_dir()).endswith("/agent-memory/advisors/feedback")


def test_feedback_archive_dir(tmp_path, monkeypatch):
    root = _make_ai_root(tmp_path)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    assert str(paths.feedback_archive_dir()).endswith("/agent-memory/advisors/feedback/archive")


def test_project_claude_dir_sibling_for_conclave_root(tmp_path, monkeypatch):
    """CLAUDE_PROJECT_DIR unset + a `.conclave` DATA root → .claude/ is the SIBLING
    (parent/.claude), not <root>/.claude inside .conclave (poststart-sweep F3 / start it-2)."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    data_root = tmp_path / ".conclave"
    data_root.mkdir()
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(data_root))
    assert paths.project_claude_dir() == tmp_path / ".claude"
    assert paths.project_agents_dir() == tmp_path / ".claude" / "agents"
    assert paths.project_skills_dir() == tmp_path / ".claude" / "skills"


def test_project_claude_dir_prefers_project_env(tmp_path, monkeypatch):
    """CLAUDE_PROJECT_DIR wins when set, regardless of the DATA root."""
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path / ".conclave"))
    assert paths.project_claude_dir() == proj / ".claude"


def test_project_claude_dir_in_repo_layout(tmp_path, monkeypatch):
    """In-repo / test layout (root not named .conclave) → <root>/.claude (unchanged)."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    root = _make_ai_root(tmp_path)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    assert paths.project_claude_dir() == root / ".claude"
