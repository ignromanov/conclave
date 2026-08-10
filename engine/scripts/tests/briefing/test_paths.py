"""Tests for briefing.paths — repo-root + canonical dir resolution."""
from pathlib import Path

import pytest

# Live-instance tests: gated by the `live_instance` marker, whose conftest fixture points
# CONCLAVE_AI_ROOT at CONCLAVE_LIVE_INSTANCE_ROOT for marked tests only. The old form gated
# on CONCLAVE_AI_ROOT itself — a variable the hermetic conftest clears — so it was asking
# whether hermeticity had been switched off, and the answer was always no (GH#105).
_NEEDS_INSTANCE = pytest.mark.live_instance

# We need the package importable; pyproject.toml is the install anchor.
# During test runs, pytest is invoked from scripts/briefing/ with PYTHONPATH set.
from briefing.paths import (
    advisors_memory_dir,
    agent_memory_dir,
    briefings_dir,
    decisions_dir,
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
def test_repo_root_holds_ops_and_its_project_holds_claude():
    """The two-root layout: ops/ is DATA, .claude/ belongs to the PROJECT beside it.

    This asserted `.claude` under repo_root() — an assumption from the `.ai/` era, when one
    directory held both (spec 103 split them). It passed anyway on a developer machine,
    because a live `.conclave` carries a generated `.claude` symlink layer (GH#109); on a
    freshly initialised instance, which has no such layer, it fails. An assertion that holds
    only where an incidental artefact exists is not testing the contract it names.
    """
    from enginelib.paths import project_root

    root = repo_root()
    assert (root / "ops").is_dir(), f"ops/ not found under DATA root {root}"
    project = project_root()
    assert (project / ".claude").is_dir(), f".claude/ not found under project root {project}"


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
def test_handoffs_dir_exists():
    d = handoffs_dir()
    assert isinstance(d, Path)
    assert d.is_dir(), f"handoffs/ not found: {d}"


@_NEEDS_INSTANCE
def test_gh_cache_dir_resolves_under_agent_memory():
    """gh-cache/ is a cache: gh-fetch creates it on first use, so an instance that has never
    fetched legitimately has none. Assert the resolved location, as the git-cache test beside
    this one already does — demanding existence would fail every fresh instance for having
    made no network call yet."""
    d = gh_cache_dir()
    assert isinstance(d, Path)
    assert d.parent == agent_memory_dir()
    assert d.name == "gh-cache"


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
    ]
    for d in dirs:
        assert str(d).startswith(str(root)), f"{d} is not under repo root {root}"
