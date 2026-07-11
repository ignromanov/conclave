"""tests/cmd/test_doctor.py — integration tests for `engine doctor` (#49c)."""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine


def _env(root: Path) -> dict:
    return {"CONCLAVE_AI_ROOT": str(root), "CLAUDE_PROJECT_DIR": ""}


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
