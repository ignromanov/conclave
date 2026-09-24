"""`engine knowledge autoload` / `rotation-worklist` (spec 110 rotation slice, GH#369)."""
from __future__ import annotations

from tests.cmd.helpers import run_engine


def _proj(tmp_path, size=50, ceiling="40"):
    data = tmp_path / ".conclave"
    data.mkdir()
    (data / "roster.yaml").write_text(
        f"knowledge:\n  autoload_ceilings:\n    .claude/progress.md: {ceiling}\n", encoding="utf-8")
    c = tmp_path / ".claude"
    c.mkdir()
    (c / "CLAUDE.md").write_text("@progress.md\n", encoding="utf-8")
    (c / "progress.md").write_text(
        "# P\n## Open\n### 3b. old — closed\n⛔ x\n" + "y" * size, encoding="utf-8")
    return {"CONCLAVE_AI_ROOT": str(data), "CLAUDE_PROJECT_DIR": str(tmp_path)}


def test_autoload_lists_files_and_check_exits_1_over_ceiling(tmp_path):
    env = _proj(tmp_path)
    r = run_engine("knowledge", "autoload", env=env)
    assert r.returncode == 0 and ".claude/progress.md" in r.stdout and "total" in r.stdout
    assert run_engine("knowledge", "autoload", "--check", env=env).returncode == 1


def test_autoload_check_exits_0_under_ceiling(tmp_path):
    env = _proj(tmp_path, size=1, ceiling="100000")
    assert run_engine("knowledge", "autoload", "--check", env=env).returncode == 0


def test_worklist_offline_names_the_closed_block_and_moves_nothing(tmp_path):
    env = _proj(tmp_path)
    before = (tmp_path / ".claude" / "progress.md").read_bytes()
    r = run_engine("knowledge", "rotation-worklist", ".claude/progress.md", "--offline", env=env)
    assert r.returncode == 0, r.stderr
    assert "candidate" in r.stdout and "3b. old" in r.stdout and "never delete" in r.stdout
    assert (tmp_path / ".claude" / "progress.md").read_bytes() == before


def test_worklist_refuses_a_file_that_is_not_auto_loaded(tmp_path):
    env = _proj(tmp_path)
    (tmp_path / "other.md").write_text("## x\n", encoding="utf-8")
    r = run_engine("knowledge", "rotation-worklist", "other.md", "--offline", env=env)
    assert r.returncode == 2 and "not auto-loaded" in r.stderr


def test_autoload_check_names_a_non_mapping_ceiling_block(tmp_path):
    env = _proj(tmp_path)
    (tmp_path / ".conclave" / "roster.yaml").write_text(
        "knowledge:\n  autoload_ceilings: 40000\n", encoding="utf-8")
    r = run_engine("knowledge", "autoload", "--check", env=env)
    assert r.returncode == 1 and "knowledge.autoload_ceilings" in r.stderr
    assert "Traceback" not in r.stderr
