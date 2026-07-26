"""tests/cmd/test_lifecycle_gh_repos.py — integration tests for `engine lifecycle gh-repos`.

B2: advisor-facing command prose built `-R "$OWNER/$(roster.py github.ai_repo)"` by hand, which
on a single-repo instance (ai_repo null) collapses to the malformed slug `owner/`. The Python
layer already resolves this correctly — roster returns "", `resolve_repos()` returns [] and the
caller refuses fail-closed — but shell had no way to reach that logic. This verb exposes it, so
the prose can iterate a resolved list instead of interpolating raw roster keys.

Hermetic: bare tmp_path via the CONCLAVE_AI_ROOT seam, plus CONCLAVE_GIT_REMOTE_CWD pointed at a
non-repo so the git-remote fallback layer cannot reach the developer's own checkout.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from tests.cmd.helpers import run_engine


def _roster(tmp: Path, body: str) -> dict:
    (tmp / "roster.yaml").write_text(textwrap.dedent(body), encoding="utf-8")
    no_repo = tmp / "not-a-repo"
    no_repo.mkdir(exist_ok=True)
    return {"CONCLAVE_AI_ROOT": str(tmp), "CONCLAVE_GIT_REMOTE_CWD": str(no_repo)}


def test_both_repos_are_owner_qualified(tmp_path):
    env = _roster(tmp_path, """
        name: Two Repo Instance
        github:
          owner: acme
          ai_repo: ops
          main_repo: app
        """)
    result = run_engine("lifecycle", "gh-repos", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["acme/ops", "acme/app"]


def test_null_ai_repo_yields_only_the_real_repo(tmp_path):
    """The B2 regression: hand-built prose emitted `acme/` here."""
    env = _roster(tmp_path, """
        name: Single Repo Instance
        github:
          owner: acme
          ai_repo: null
          main_repo: app
        """)
    result = run_engine("lifecycle", "gh-repos", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["acme/app"]


def test_qualified_slug_passes_through(tmp_path):
    env = _roster(tmp_path, """
        name: Qualified Instance
        github:
          owner: acme
          ai_repo: someone-else/ops
          main_repo: app
        """)
    result = run_engine("lifecycle", "gh-repos", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["someone-else/ops", "acme/app"]


def test_no_scope_refuses_rather_than_printing_nothing(tmp_path):
    """An empty list must not read as success — a `for` loop over it is a silent no-op."""
    env = _roster(tmp_path, """
        name: Unscoped Instance
        github:
          owner: acme
          ai_repo: null
          main_repo: null
        """)
    result = run_engine("lifecycle", "gh-repos", env=env)
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert "no repo scope" in result.stderr
