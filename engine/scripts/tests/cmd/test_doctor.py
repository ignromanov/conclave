"""tests/cmd/test_doctor.py — integration tests for `engine doctor` (#49c)."""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine


def _env(root: Path) -> dict:
    """Pin every root the doctor code path reaches, not just the DATA one.

    The adapter also resolves `paths.engine_root()` (for the merge-base check, #58), and
    that one is derived from the module's own location unless CONCLAVE_ENGINE_ROOT says
    otherwise. Left unset, these tests read the branch layout of whatever checkout they
    happen to run in, and `test_fix_seeds_and_exits_0` fails on a developer machine with
    a stranded branch while passing in CI — isolation that pins one resolver out of two
    is how a green suite ends up weaker than the environment it claims to model.

    The target deliberately does not exist: a non-repo yields nothing to report, which is
    what a hermetic run should see.
    """
    return {
        "CONCLAVE_AI_ROOT": str(root),
        "CLAUDE_PROJECT_DIR": "",
        "CONCLAVE_ENGINE_ROOT": str(root / "no-engine-checkout"),
    }


def _mk_root(tmp_path: Path) -> Path:
    (tmp_path / "agent-memory").mkdir(parents=True)
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    return tmp_path


def test_missing_hot_exits_1(tmp_path):
    root = _mk_root(tmp_path)
    r = run_engine("doctor", env=_env(root))
    assert r.returncode == 1
    assert "hot.md" in r.stdout
    assert "FAIL" in r.stdout


def test_fix_seeds_and_exits_0(tmp_path):
    root = _mk_root(tmp_path)
    (root / ".claude" / "agents" / "sage-cto.md").write_text("# a\n")
    r = run_engine("doctor", "--fix", "--advisor", "sage-cto", env=_env(root))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (root / "agent-memory" / "hot.md").is_file()
    assert "advisor:sage-cto" in r.stdout


def test_unknown_advisor_exits_1(tmp_path):
    root = _mk_root(tmp_path)
    (root / "agent-memory" / "hot.md").write_text(
        "## Now\n\n## Open threads\n\n## Recent decisions\n\n## Watch\n"
    )
    r = run_engine("doctor", "--advisor", "ghost", env=_env(root))
    assert r.returncode == 1
    assert "not in registry" in r.stdout
