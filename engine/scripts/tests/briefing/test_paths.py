"""Tests for briefing.paths — repo-root + canonical dir resolution."""
import os
from pathlib import Path

import pytest

# Skip live-instance tests when no instance root is available (D3).
_NEEDS_INSTANCE = pytest.mark.skipif(
    not (os.environ.get("CONCLAVE_AI_ROOT") or os.environ.get("VOIDPAY_AI_ROOT")),
    reason="needs live instance root",
)

# We need the package importable; pyproject.toml is the install anchor.
# During test runs, pytest is invoked from scripts/briefing/ with PYTHONPATH set.
from briefing.paths import (
    advisors_memory_dir,
    agent_memory_dir,
    briefings_dir,
    decisions_dir,
    feedback_dir,
    gh_cache_dir,
    git_cache_dir,
    handoffs_dir,
    hot_md_path,
    mentions_dir,
    repo_root,
    run_log_dir,
    sessions_dir,
    templates_dir,
)


@_NEEDS_INSTANCE
def test_repo_root_returns_path():
    root = repo_root()
    assert isinstance(root, Path)


@_NEEDS_INSTANCE
def test_repo_root_has_ops_and_claude():
    root = repo_root()
    assert (root / "ops").is_dir(), f"ops/ not found under {root}"
    assert (root / ".claude").exists(), f".claude not found under {root}"


def test_repo_root_env_override(monkeypatch, tmp_path):
    import briefing.paths as _paths

    # Create a fake root with ops/ and .claude/
    (tmp_path / "ops").mkdir()
    (tmp_path / ".claude").mkdir()
    # Clear module cache so env override takes effect.
    monkeypatch.setattr(_paths, "_REPO_ROOT_CACHE", None)
    monkeypatch.setenv("VOIDPAY_AI_ROOT", str(tmp_path))
    root = repo_root()
    assert root == tmp_path.resolve()


def test_repo_root_plugin_mode_defaults_to_project_conclave(monkeypatch, tmp_path):
    import briefing.paths as _paths

    monkeypatch.setattr(_paths, "_REPO_ROOT_CACHE", None)
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("VOIDPAY_AI_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert repo_root() == (tmp_path / ".conclave").resolve()


def test_engine_root_plugin_mode_defaults_to_plugin_engine_subtree(monkeypatch, tmp_path):
    from briefing.paths import engine_root

    monkeypatch.delenv("CONCLAVE_ENGINE_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert engine_root() == (tmp_path / "engine").resolve()


@_NEEDS_INSTANCE
def test_agent_memory_dir_exists():
    d = agent_memory_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"agent-memory/ not found: {d}"


@_NEEDS_INSTANCE
def test_advisors_memory_dir_exists():
    d = advisors_memory_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"advisors/ not found: {d}"


@_NEEDS_INSTANCE
def test_briefings_dir_exists():
    d = briefings_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"briefings/ not found: {d}"


@_NEEDS_INSTANCE
def test_sessions_dir_exists():
    d = sessions_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"sessions/ not found: {d}"


@_NEEDS_INSTANCE
def test_decisions_dir_exists():
    d = decisions_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"decisions/ not found: {d}"


@_NEEDS_INSTANCE
def test_mentions_dir_exists():
    d = mentions_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"mentions/ not found: {d}"


@_NEEDS_INSTANCE
def test_feedback_dir_exists():
    d = feedback_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"feedback/ not found: {d}"


@_NEEDS_INSTANCE
def test_handoffs_dir_exists():
    d = handoffs_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"handoffs/ not found: {d}"


@_NEEDS_INSTANCE
def test_gh_cache_dir_exists():
    d = gh_cache_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"gh-cache/ not found: {d}"


@_NEEDS_INSTANCE
def test_git_cache_dir_exists():
    d = git_cache_dir()
    assert isinstance(d, Path)
    # git-cache may not exist yet — only assert it is a Path under agent-memory/
    assert str(d).endswith("git-cache")


@_NEEDS_INSTANCE
def test_run_log_dir_exists():
    d = run_log_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"run-log/ not found: {d}"


def test_templates_dir_exists():
    d = templates_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"templates/ not found: {d}"


@_NEEDS_INSTANCE
def test_hot_md_path_is_file():
    p = hot_md_path()
    assert isinstance(p, Path)
    assert p.name == "hot.md"


@_NEEDS_INSTANCE
def test_all_dirs_are_under_repo_root():
    root = repo_root()
    dirs = [
        agent_memory_dir(),
        advisors_memory_dir(),
        briefings_dir(),
        sessions_dir(),
        decisions_dir(),
        mentions_dir(),
        feedback_dir(),
    ]
    for d in dirs:
        assert str(d).startswith(str(root)), f"{d} is not under repo root {root}"
