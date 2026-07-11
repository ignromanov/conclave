"""tests/cmd/test_audit_scope_collision.py — integration tests for `engine audit scope-collision`.

Ports the 3 scenarios from audit-scope-collision.test.sh + adds 1 new R6 cross-dir case.
Uses bare tmp_path (no ai_root fixture) and --agents-dir overrides throughout.
"""
from tests.cmd.helpers import run_engine


def _make_agent(agents_dir, name: str, owns_list: list[str]) -> None:
    """Write a minimal agent .md with block-list owns: frontmatter."""
    agents_dir.mkdir(parents=True, exist_ok=True)
    owns_block = "\n".join(f"  - {tok}" for tok in owns_list)
    text = f"---\nname: {name}\nowns:\n{owns_block}\n---\nBody.\n"
    (agents_dir / f"{name}.md").write_text(text)


def test_collision_exit3(tmp_path):
    """Case 1 (.test.sh): two agents in one dir both claiming the same token → exit 3, token printed."""
    agents = tmp_path / "agents"
    _make_agent(agents, "exec.alpha", ["p1-research-artifact", "unique-to-alpha"])
    _make_agent(agents, "exec.beta", ["p1-research-artifact", "unique-to-beta"])
    r = run_engine("audit", "scope-collision", "--agents-dir", str(agents))
    assert r.returncode == 3
    assert "p1-research-artifact" in r.stdout


def test_disjoint_exit0(tmp_path):
    """Case 2 (.test.sh): two agents with distinct owns → exit 0 (no collision)."""
    agents = tmp_path / "agents"
    _make_agent(agents, "exec.alpha", ["artifact-a"])
    _make_agent(agents, "exec.beta", ["artifact-b"])
    r = run_engine("audit", "scope-collision", "--agents-dir", str(agents))
    assert r.returncode == 0


def test_missing_dir_exit1(tmp_path):
    """Case 3 (.test.sh): non-existent --agents-dir with no other dir → exit 1."""
    nonexistent = tmp_path / "nonexistent-agents-dir"
    r = run_engine("audit", "scope-collision", "--agents-dir", str(nonexistent))
    assert r.returncode == 1


def test_cross_dir_collision_exit3(tmp_path):
    """Case 4 (R6 new): token owned by agent A in dir1 and agent B in dir2 → exit 3, token printed."""
    dir1 = tmp_path / "dir1"
    dir2 = tmp_path / "dir2"
    _make_agent(dir1, "agent-a", ["shared-token"])
    _make_agent(dir2, "agent-b", ["shared-token"])
    r = run_engine(
        "audit", "scope-collision",
        "--agents-dir", str(dir1),
        "--agents-dir", str(dir2),
    )
    assert r.returncode == 3
    assert "shared-token" in r.stdout
