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

from tests.cmd.helpers import non_repo_dir, run_engine


def _roster(tmp: Path, body: str) -> dict:
    (tmp / "roster.yaml").write_text(textwrap.dedent(body), encoding="utf-8")
    # non_repo_dir asserts the premise instead of inheriting it from wherever tmp_path
    # happens to sit — a basetemp inside a checkout would let git walk up and the pin
    # would silently stop being one.
    return {
        "CONCLAVE_AI_ROOT": str(tmp),
        "CONCLAVE_GIT_REMOTE_CWD": str(non_repo_dir(tmp)),
    }


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


def test_null_owner_refuses_instead_of_emitting_a_leading_slash(tmp_path):
    """The verb's own version of the defect it was built to close: with `owner: null`,
    `f"{owner}/{repo}"` emitted `/app` and exited 0, so the prose ran `gh -R "/app"`."""
    env = _roster(tmp_path, """
        name: Null Owner Instance
        github:
          owner: null
          ai_repo: null
          main_repo: app
        """)
    result = run_engine("lifecycle", "gh-repos", env=env)
    assert result.returncode == 1
    assert result.stdout.strip() == ""
    assert "no usable repo scope" in result.stderr
    # This roster DECLARED main_repo, so the refusal must name the typo, not imply a null
    # roster — the operator has to know which key to fix.
    assert "github.main_repo" in result.stderr, result.stderr
    assert "'/app'" in result.stderr, result.stderr
    # Positive control for the negative assertion in the declared-nothing test below: that one
    # proves no `roster:`-prefixed line is emitted, which is only meaningful if such a line is
    # emitted HERE. Asserting both directions keeps either from passing vacuously.
    assert [ln for ln in result.stderr.splitlines() if ln.startswith("roster:")], result.stderr


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
    assert "no usable repo scope" in result.stderr
    # Declared nothing: there is no typo to report, so no per-key diagnostic either.
    # Match the diagnostic's SHAPE — a line that STARTS `roster:`, as the emitter writes it.
    # A bare `"roster:" not in stderr` collides with the generic refusal, which quotes the
    # word while pointing the operator at the diagnostic, and so cannot tell "none emitted"
    # from "mentioned in passing".
    assert not [ln for ln in result.stderr.splitlines() if ln.startswith("roster:")], result.stderr
