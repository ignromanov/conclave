"""tests/cmd/test_audit_registry_consistency.py — integration tests for `engine audit registry-consistency`."""
from tests.cmd.helpers import run_engine


def _make_env(tmp_path):
    return {"CONCLAVE_AI_ROOT": str(tmp_path)}


def test_symmetric_mentioned_is_clean(tmp_path):
    """Advisor with skill + agent + mentioned in CLAUDE.md → 0 CRIT, 0 WARN, exit 0."""
    (tmp_path / ".claude" / "skills" / "team.alpha").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "team.alpha" / "SKILL.md").write_text("# team.alpha\n")
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "team.alpha.md").write_text("# team.alpha\n")
    (tmp_path / ".claude" / "CLAUDE.md").write_text("team.alpha is a great advisor\n")
    r = run_engine("audit", "registry-consistency", env=_make_env(tmp_path))
    assert r.returncode == 0
    assert "0 CRIT" in r.stdout
    assert "0 WARN" in r.stdout


def test_skill_without_agent_is_crit(tmp_path):
    """Skill dir exists but no agents/*.md → CRIT, exit 1. Symmetry keyed on bare id
    (#54): the message reports the bare advisor id, not the full dir-name."""
    (tmp_path / ".claude" / "skills" / "team.beta").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "team.beta" / "SKILL.md").write_text("# team.beta\n")
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "CLAUDE.md").write_text("team.beta\n")
    r = run_engine("audit", "registry-consistency", env=_make_env(tmp_path))
    assert r.returncode == 1
    assert "beta has skill but no agents/*.md" in r.stdout


def test_agent_without_skill_is_crit(tmp_path):
    """Agent file exists but no skill dir → CRIT, exit 1 (bare-id symmetry, #54)."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "team.gamma.md").write_text("# team.gamma\n")
    (tmp_path / ".claude" / "CLAUDE.md").write_text("team.gamma\n")
    r = run_engine("audit", "registry-consistency", env=_make_env(tmp_path))
    assert r.returncode == 1
    assert "gamma in agents/ but no skill dir" in r.stdout


def test_skill_not_in_claude_md_is_warn(tmp_path):
    """Advisor has skill+agent but name absent from CLAUDE.md → WARN, exit 2."""
    (tmp_path / ".claude" / "skills" / "team.delta").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "team.delta" / "SKILL.md").write_text("# team.delta\n")
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "team.delta.md").write_text("# team.delta\n")
    (tmp_path / ".claude" / "CLAUDE.md").write_text("nothing relevant here\n")
    r = run_engine("audit", "registry-consistency", env=_make_env(tmp_path))
    assert r.returncode == 2
    assert "delta not mentioned in CLAUDE.md" in r.stdout


# --- #54: current-layout discovery (conclave-<id> skill + bare <id>.md agent) ---

def test_conclave_skill_without_agent_is_crit(tmp_path):
    """A conclave-<id> skill with no agent-def is flagged — pre-#54 the team.*/SKILL.md
    glob missed conclave- dirs, so the skill was silently invisible."""
    (tmp_path / ".claude" / "skills" / "conclave-omega").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "conclave-omega" / "SKILL.md").write_text("# omega\n")
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "CLAUDE.md").write_text("omega\n")
    r = run_engine("audit", "registry-consistency", env=_make_env(tmp_path))
    assert r.returncode == 1
    assert "omega has skill but no agents/*.md" in r.stdout


def test_bare_agent_without_skill_is_crit(tmp_path):
    """A bare <id>.md agent-def (current mint) with no skill dir is flagged — pre-#54
    the team.*.md glob only matched legacy-prefixed agent files, missing bare ones."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "zeta.md").write_text("# zeta\n")
    (tmp_path / ".claude" / "CLAUDE.md").write_text("zeta\n")
    r = run_engine("audit", "registry-consistency", env=_make_env(tmp_path))
    assert r.returncode == 1
    assert "zeta in agents/ but no skill dir" in r.stdout


def test_conclave_skill_with_bare_agent_is_symmetric(tmp_path):
    """Current layout end-to-end: conclave-<id> skill + bare <id>.md agent + mention →
    symmetric, 0 CRIT / 0 WARN. Guards against re-introducing a prefix mismatch."""
    (tmp_path / ".claude" / "skills" / "conclave-omega").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "conclave-omega" / "SKILL.md").write_text("# omega\n")
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "omega.md").write_text("# omega\n")
    (tmp_path / ".claude" / "CLAUDE.md").write_text("omega is hired\n")
    r = run_engine("audit", "registry-consistency", env=_make_env(tmp_path))
    assert r.returncode == 0
    assert "0 CRIT" in r.stdout
    assert "0 WARN" in r.stdout


def test_exec_agent_def_excluded(tmp_path):
    """exec-*.md agent-defs are executors, not advisors — never flagged as skill-less."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "exec-scout-research.md").write_text("# exec-scout-research\n")
    (tmp_path / ".claude" / "CLAUDE.md").write_text("nothing\n")
    r = run_engine("audit", "registry-consistency", env=_make_env(tmp_path))
    assert r.returncode == 0
    assert "exec-scout-research" not in r.stdout


def test_lifecycle_skill_ignored(tmp_path):
    """team.forge (lifecycle) with skill+agent but absent from CLAUDE.md → no findings, exit 0."""
    (tmp_path / ".claude" / "skills" / "team.forge").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "team.forge" / "SKILL.md").write_text("# team.forge\n")
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "team.forge.md").write_text("# team.forge\n")
    (tmp_path / ".claude" / "CLAUDE.md").write_text("no advisors mentioned\n")
    r = run_engine("audit", "registry-consistency", env=_make_env(tmp_path))
    assert r.returncode == 0
    assert "0 CRIT" in r.stdout
    assert "0 WARN" in r.stdout
