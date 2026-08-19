"""test_data_resolver.py — DATA/ENGINE root resolution under the plugin (098 D-5).

Under Claude Code the plugin runs with CLAUDE_PROJECT_DIR (the consumer repo) and
CLAUDE_PLUGIN_ROOT (the plugin install dir) set. In that mode enginelib/paths.py defaults
DATA to `${CLAUDE_PROJECT_DIR}/.conclave` and ENGINE to `${CLAUDE_PLUGIN_ROOT}/engine`
(the engine subtree, so `${ENGINE_ROOT}/scripts` resolves the unified package that
stays at engine/scripts/). Outside CC those vars are absent, the defaults stay empty,
and repo_root()/engine_root() fall through to the filesystem walk unchanged.

Ported from subprocess/bash to direct in-process calls (Task 3E.9, Wave-3 gate closure).
"""
import pathlib

import pytest

from enginelib import paths

# Both roots are `.resolve()`d, so expectations are resolved too. That is not a test
# nicety: on macOS /tmp and /var are symlinks, and the two resolvers' disagreement about
# resolving made every path either produced differ from the other's by a /private prefix
# — the same directory under two spellings, unequal under `==`.


def test_data_root_defaults_to_project_conclave(monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/tmp/proj")
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    assert paths.repo_root() == pathlib.Path("/tmp/proj/.conclave").resolve()


def test_engine_root_defaults_to_plugin_engine_subtree(monkeypatch):
    # Interfaces (plan §D-5) + layout: scripts live at ${CLAUDE_PLUGIN_ROOT}/engine/scripts,
    # so ENGINE_ROOT is the engine subtree, NOT the bare plugin root.
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/tmp/plug")
    monkeypatch.delenv("CONCLAVE_ENGINE_ROOT", raising=False)
    assert paths.engine_root() == pathlib.Path("/tmp/plug/engine").resolve()


def test_explicit_data_root_wins_over_plugin_default(monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", "/explicit/data")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/tmp/proj")
    assert paths.repo_root() == pathlib.Path("/explicit/data").resolve()


def test_legacy_alias_alone_raises_rather_than_resolving(monkeypatch, tmp_path):
    """The retired alias, set without CONCLAVE_AI_ROOT, must stop the process.

    Six call sites read it and disagreed about whether it counted, so a process could
    honour it in one subsystem and ignore it in the next — writing into one tree while
    reading from another, with every individual call succeeding.
    """
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setenv("VOIDPAY_AI_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError, match="VOIDPAY_AI_ROOT is set but CONCLAVE_AI_ROOT"):
        paths.repo_root()


def test_legacy_alias_is_inert_beside_the_current_name(monkeypatch):
    """Set alongside CONCLAVE_AI_ROOT it is ignored, not an error — which is what the
    test fixtures did for years and what an operator mid-migration will have."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", "/explicit/data")
    monkeypatch.setenv("VOIDPAY_AI_ROOT", "/some/other/tree")
    assert paths.repo_root() == pathlib.Path("/explicit/data").resolve()


def test_no_claude_env_leaves_data_root_to_walk(tmp_path, monkeypatch):
    # Outside Claude Code (no CLAUDE_PROJECT_DIR) the resolver must NOT inject a
    # default — repo_root()'s filesystem walk stays authoritative.
    # Bash semantic: CONCLAVE_AI_ROOT was empty-string (no default injected).
    # Python semantic: _plugin_data_default() returns None (same absence of default),
    # and the walk runs — raising RuntimeError when no ops/+.claude/ siblings are found.
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("VOIDPAY_AI_ROOT", raising=False)
    assert paths._plugin_data_default() is None
    with pytest.raises(RuntimeError):
        paths.repo_root(start=tmp_path)
