"""tests/cmd/test_find_references.py — integration tests for `engine find references`.

Ports the 1 case from find-references.test.sh and extends to 4 cases.
Uses a bare tmp_path seeded manually; CONCLAVE_ENGINE_ROOT points there so that
engine_root()/.claude is the seeded tree.
"""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine


def _env(tmp_path: Path) -> dict:
    return {"CONCLAVE_ENGINE_ROOT": str(tmp_path)}


def test_match_in_dot_claude(tmp_path):
    """Case 1: match inside .claude/ → exit 0, non-empty stdout, correct path + line."""
    cmd_dir = tmp_path / ".claude" / "commands"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "start.md").write_text("Call /team.start to begin.\n")

    r = run_engine("find", "references", r"/team\.start", env=_env(tmp_path))

    assert r.returncode == 0
    assert r.stdout.strip() != ""
    assert "start.md" in r.stdout
    assert "/team.start" in r.stdout


def test_match_in_claude_md(tmp_path):
    """Case 2: match in CLAUDE.md → the CLAUDE.md path appears in output."""
    (tmp_path / "CLAUDE.md").write_text("UNIQUE_TOKEN_XYZ_42 lives here.\n")

    r = run_engine("find", "references", "UNIQUE_TOKEN_XYZ_42", env=_env(tmp_path))

    assert r.returncode == 0
    assert "CLAUDE.md" in r.stdout
    assert "UNIQUE_TOKEN_XYZ_42" in r.stdout


def test_no_match_empty_stdout(tmp_path):
    """Case 3: no match → exit 0 AND stdout empty."""
    dot_claude = tmp_path / ".claude"
    dot_claude.mkdir()
    (dot_claude / "notes.md").write_text("nothing interesting here\n")

    r = run_engine("find", "references", "PATTERN_THAT_WILL_NEVER_MATCH_XYZZY", env=_env(tmp_path))

    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_excluded_dirs_pruned(tmp_path):
    """Case 4: token in node_modules/ is absent; same token in normal file is present.

    Proves that the prune ({.git, archive, node_modules}) works correctly.
    """
    token = "PRUNE_TEST_TOKEN_99"

    # Normal (should match)
    normal_dir = tmp_path / ".claude" / "commands"
    normal_dir.mkdir(parents=True)
    (normal_dir / "normal.md").write_text(f"Reference to {token} here.\n")

    # Excluded (should NOT match)
    excluded_dir = tmp_path / ".claude" / "node_modules"
    excluded_dir.mkdir(parents=True)
    (excluded_dir / "x.md").write_text(f"Reference to {token} in excluded dir.\n")

    archive_dir = tmp_path / ".claude" / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "y.md").write_text(f"Reference to {token} in archive dir.\n")

    r = run_engine("find", "references", token, env=_env(tmp_path))

    assert r.returncode == 0
    # Normal hit present
    assert "normal.md" in r.stdout
    # Excluded hits absent
    assert "node_modules" not in r.stdout
    assert "archive" not in r.stdout
