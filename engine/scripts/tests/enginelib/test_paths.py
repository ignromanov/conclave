from pathlib import Path

import pytest

from enginelib import paths


def _make_ai_root(tmp_path: Path) -> Path:
    root = tmp_path / ".ai"
    (root / "ops").mkdir(parents=True)
    (root / ".claude").mkdir(parents=True)
    # roster.yaml is what makes this an instance root rather than the shape of the
    # engine checkout, which also carries ops/ beside .claude/ (GH#29).
    (root / "roster.yaml").write_text("github: {}\n", encoding="utf-8")
    return root


def test_repo_root_from_env(tmp_path, monkeypatch):
    root = _make_ai_root(tmp_path)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    assert paths.repo_root() == root


def test_advisors_memory_dir_absolute(tmp_path, monkeypatch):
    root = _make_ai_root(tmp_path)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    assert str(paths.advisors_memory_dir()).endswith("/agent-memory/advisors")


def test_checkpoints_dir_is_a_sibling_of_sessions_not_a_child(tmp_path, monkeypatch):
    """Spec 117 T1. The shape is the requirement, not the existence.

    Seven modules call `sessions_dir()` and read every `*.md` under it as a session that
    has ENDED (measured: 8 non-test files reference it, one of which is its definition).
    Nest the checkpoints under it and each one becomes a closed session record that no
    close ever wrote — the briefing's session count, the memory index and the rename plan
    all take the in-flight file as history.

    So the assertion is the parent, not the path: a test spelling only
    `endswith("/checkpoints")` passes with `sessions/checkpoints/`, which is the failure
    this pins. It reddens both ways — remove `checkpoints_dir` and it errors, re-root it
    under `sessions_dir()` and the parent assertion fails.
    """
    root = _make_ai_root(tmp_path)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    assert paths.checkpoints_dir().parent == paths.advisors_memory_dir()
    assert paths.checkpoints_dir() != paths.sessions_dir()
    assert not paths.checkpoints_dir().is_relative_to(paths.sessions_dir())


def test_scaffolder_creates_the_checkpoints_dir():
    """R1 needs the directory before the first verb runs, so the scaffolder owns it.

    Create-on-first-write is the wrong discipline here: `session_init` writes the open
    record, and R1 forbids that write from being able to fail a session start. A
    directory the scaffolder made cannot be the reason a start fails.
    """
    from init.conclave_init import DATA_SUBDIRS

    assert "agent-memory/advisors/checkpoints" in DATA_SUBDIRS


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


def test_repo_root_walk_refuses_a_tree_without_a_roster(tmp_path, monkeypatch):
    """ops/ + .claude/ alone is the engine checkout's shape. The old marker matched it,
    so with no env set the resolver answered with the CODE tree and DATA was written
    into it (GH#29) — the heuristic confirmed itself from the tree it read itself from."""
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    code_like = tmp_path / "checkout"
    (code_like / "ops").mkdir(parents=True)
    (code_like / ".claude").mkdir(parents=True)
    assert paths.walk_for_data_root(code_like) is None
    with pytest.raises(RuntimeError, match="unable to locate"):
        paths.repo_root(start=code_like)
