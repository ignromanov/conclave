"""test_known_advisors.py — shared registry-driven advisor discovery (#47).

Promotes session_init._known_advisors to enginelib.advisors.known_advisors(root):
an explicit-root glob of .claude/agents/*.md that resolves the .conclave-sibling
layout WITHOUT relying on CLAUDE_PROJECT_DIR, excluding forge (META) + exec-*.
No hardcoded CANONICAL_ADVISORS fallthrough.
"""


from enginelib.advisors import known_advisors


def _write_agent(agents_dir, stem):
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{stem}.md").write_text("---\nname: x\n---\n")


def test_discovers_hired_flat_advisor(tmp_path, monkeypatch):
    """A hired advisor at <root>/.claude/agents/<id>.md is discovered."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    _write_agent(tmp_path / ".claude" / "agents", "sage-cto")
    assert known_advisors(tmp_path) == {"sage-cto"}


def test_excludes_forge_and_exec(tmp_path, monkeypatch):
    """forge (META) and exec-* (executors) are not advisors."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    agents = tmp_path / ".claude" / "agents"
    for stem in ("sage-cto", "forge", "exec-atlas-dev", "exec-themis-judge"):
        _write_agent(agents, stem)
    assert known_advisors(tmp_path) == {"sage-cto"}


def test_resolves_conclave_sibling(tmp_path, monkeypatch):
    """When root is a `.conclave` DATA root, agents live in the SIBLING
    root.parent/.claude/agents — resolved WITHOUT CLAUDE_PROJECT_DIR."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    project = tmp_path
    _write_agent(project / ".claude" / "agents", "kai-cto")
    data_root = project / ".conclave"
    data_root.mkdir()
    assert known_advisors(data_root) == {"kai-cto"}


def test_empty_when_no_agents_dir(tmp_path, monkeypatch):
    """No agents dir → empty set, never a hardcoded VoidPay fallthrough."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert known_advisors(tmp_path) == set()


def test_claude_project_dir_overrides_root(tmp_path, monkeypatch):
    """CLAUDE_PROJECT_DIR wins over the passed root (router/hook binding)."""
    project = tmp_path / "proj"
    _write_agent(project / ".claude" / "agents", "nexus-ceo")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    other_root = tmp_path / "unrelated" / ".conclave"
    other_root.mkdir(parents=True)
    assert known_advisors(other_root) == {"nexus-ceo"}
