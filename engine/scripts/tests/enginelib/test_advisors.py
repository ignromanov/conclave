"""test_advisors.py — port of tests/lib-advisors-lifecycle.bats (4 cases) + enumeration test."""

from enginelib.advisors import canonical_advisors, is_canonical_advisor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_skills(tmp_path, names):
    """Create tmp engine root with skills/team.<name>/SKILL.md for each name."""
    for name in names:
        skill_dir = tmp_path / "skills" / f"team.{name}"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(f"# {name}\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Bats case 1: lifecycle sentinel is canonical when allow_lifecycle=True
# ---------------------------------------------------------------------------

def test_lifecycle_sentinel_allowed_with_flag(monkeypatch, tmp_path):
    """Port: is_canonical_advisor "lifecycle" --allow-lifecycle → exit 0."""
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(tmp_path))
    (tmp_path / "skills").mkdir()
    assert is_canonical_advisor("lifecycle", allow_lifecycle=True) is True


# ---------------------------------------------------------------------------
# Bats case 2: lifecycle sentinel rejected by default
# ---------------------------------------------------------------------------

def test_lifecycle_sentinel_rejected_by_default(monkeypatch, tmp_path):
    """Port: is_canonical_advisor "lifecycle" → exit non-0."""
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(tmp_path))
    (tmp_path / "skills").mkdir()
    assert is_canonical_advisor("lifecycle") is False


# ---------------------------------------------------------------------------
# Bats case 3: --allow-lifecycle does not weaken non-lifecycle check
# ---------------------------------------------------------------------------

def test_allow_lifecycle_does_not_weaken_nonlifecycle_check(monkeypatch, tmp_path):
    """Port: is_canonical_advisor "totally-fake-name" --allow-lifecycle → exit non-0."""
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(tmp_path))
    (tmp_path / "skills").mkdir()
    assert is_canonical_advisor("totally-fake-name", allow_lifecycle=True) is False


# ---------------------------------------------------------------------------
# Bats case 4: flag-first ordering (CLI adapter concern — deferred to Wave 3)
# At the function level this is the same kwarg call as case 1.
# Note: the bats test verified that `--allow-lifecycle` could appear before the
# name in the CLI (flag-first ordering). That is a Wave 3 CLI adapter concern;
# at the enginelib level the kwarg call is identical to case 1.
# ---------------------------------------------------------------------------

def test_flag_first_ordering_kwarg_equivalent(monkeypatch, tmp_path):
    """Port: is_canonical_advisor --allow-lifecycle lifecycle → exit 0.
    CLI arg-ordering is a Wave 3 adapter concern; the kwarg call is case 1.
    """
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(tmp_path))
    (tmp_path / "skills").mkdir()
    assert is_canonical_advisor(name="lifecycle", allow_lifecycle=True) is True


# ---------------------------------------------------------------------------
# Positive enumeration: canonical_advisors excludes lifecycle, returns sorted list
# ---------------------------------------------------------------------------

def test_canonical_advisors_enumeration_and_exclusion(monkeypatch, tmp_path):
    """Seed team.kai-cto, team.forge (lifecycle→excluded), team.dev.
    Expect canonical_advisors() == ["dev", "kai-cto"] (sorted, forge excluded).
    """
    _seed_skills(tmp_path, ["kai-cto", "forge", "dev"])
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(tmp_path))
    result = canonical_advisors()
    assert result == ["dev", "kai-cto"]


def test_canonical_advisors_discovers_conclave_prefix(monkeypatch, tmp_path):
    """#54: the skills-glob half must also see current-layout conclave-<id> dirs,
    not just legacy team.<id>. Lifecycle (conclave-start) still excluded by bare id."""
    for dirname in ("conclave-growth", "conclave-start", "team.kai-cto"):
        d = tmp_path / "skills" / dirname
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# x\n")
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(tmp_path))
    result = canonical_advisors()
    assert "growth" in result and "kai-cto" in result
    assert "start" not in result  # lifecycle excluded even under conclave- prefix


# ---------------------------------------------------------------------------
# ER1: discovery union across legacy skills_dir(), plugin agents/*.md,
# project .claude/agents/*.md — normalized (team. stripped, exec-* excluded, deduped)
# ---------------------------------------------------------------------------

def _seed(tmp_path, monkeypatch, *, skills=(), plugin_agents=(), project_agents=()):
    """Control all three discovery roots hermetically."""
    engine = tmp_path / "engine"
    (engine / "skills").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine))       # engine_root -> skills_dir + plugin_agents(parent/agents)
    for n in skills:
        d = engine / "skills" / f"team.{n}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"# {n}\n")
    ag = tmp_path / "agents"                                       # plugin_agents_dir == engine.parent/agents == tmp_path/agents
    ag.mkdir(exist_ok=True)
    for fn in plugin_agents:
        (ag / fn).write_text("---\nname: x\n---\n")
    proj = tmp_path / "project"
    pa = proj / ".claude" / "agents"
    pa.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))            # project_agents_dir
    for fn in project_agents:
        (pa / fn).write_text("---\nname: x\n---\n")


def test_forge_is_advisor(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, plugin_agents=["forge.md", "exec-scout-research.md"])
    assert is_canonical_advisor("forge") is True


def test_exec_excluded(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, plugin_agents=["forge.md", "exec-scout-research.md", "exec-themis-judge.md"])
    ids = canonical_advisors()
    assert "exec-scout-research" not in ids and "exec-themis-judge" not in ids


def test_project_flat_advisor_discovered(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, project_agents=["iris.md"])
    assert "iris" in canonical_advisors()


def test_legacy_skill_dir_discovered(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, skills=["growth"])
    assert "growth" in canonical_advisors()


def test_legacy_agentdef_team_prefix_normalized(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, project_agents=["team.privacy-trust.md"])
    assert "privacy-trust" in canonical_advisors()
    assert "team.privacy-trust" not in canonical_advisors()


def test_dual_form_dedupes(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, skills=["growth"], project_agents=["team.growth.md"])
    assert canonical_advisors().count("growth") == 1


# ---------------------------------------------------------------------------
# Regression: discovery must not consult project_agents_dir() when
# CLAUDE_PROJECT_DIR is unset. In dev/test, project_agents_dir() falls back
# to repo_root(), whose ops+.claude ancestor-walk can escape a worktree into
# a sibling checkout and silently union unrelated agent-defs. No
# RuntimeError fires in that case, so the previous try/except guard never
# engaged. Fix: skip the project-agents source entirely unless
# CLAUDE_PROJECT_DIR is set explicitly.
# ---------------------------------------------------------------------------

def test_discovery_skips_project_agents_without_claude_project_dir(tmp_path, monkeypatch):
    engine = tmp_path / "engine"
    (engine / "skills" / "team.growth").mkdir(parents=True, exist_ok=True)
    (engine / "skills" / "team.growth" / "SKILL.md").write_text("# growth\n")
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine))

    ag = tmp_path / "agents"                      # plugin_agents_dir == engine.parent/agents
    ag.mkdir()
    (ag / "forge.md").write_text("---\nname: x\n---\n")

    # An escapable "repo root" reachable via repo_root()'s ops+.claude
    # ancestor-walk from cwd, seeded with a stray project agent-def that
    # must NOT be discovered when CLAUDE_PROJECT_DIR is unset.
    fake_root = tmp_path / "fake-checkout"
    (fake_root / "ops").mkdir(parents=True)
    (fake_root / ".claude" / "agents").mkdir(parents=True)
    (fake_root / ".claude" / "agents" / "rogue.md").write_text("---\nname: x\n---\n")

    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.chdir(fake_root)

    result = canonical_advisors()
    assert "rogue" not in result
    assert "forge" in result
    assert "growth" in result


# ---------------------------------------------------------------------------
# #24: real sessions export CONCLAVE_AI_ROOT (SessionStart hook), not
# CLAUDE_PROJECT_DIR. canonical_advisors() must trust that anchor too, or a
# hired advisor's session close ("is not canonical") rejects a real def.
# ---------------------------------------------------------------------------

def test_conclave_ai_root_unions_project_agents_without_claude_project_dir(tmp_path, monkeypatch):
    """#24: real sessions export CONCLAVE_AI_ROOT, not CLAUDE_PROJECT_DIR."""
    engine = tmp_path / "engine"
    (engine / "skills").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine))

    proj = tmp_path / "project"
    pa = proj / ".claude" / "agents"
    pa.mkdir(parents=True, exist_ok=True)
    (pa / "sage-cto.md").write_text("---\nname: x\n---\n")

    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(proj))

    assert "sage-cto" in canonical_advisors()


# ---------------------------------------------------------------------------
# ER1 AC1: create -> discover round-trip. A freshly `advisor.create`-d flat
# advisor must be immediately recognized by is_canonical_advisor.
# ---------------------------------------------------------------------------

def test_created_advisor_is_canonical_and_files(tmp_path, monkeypatch):
    """ER1 AC1: a freshly created flat advisor passes the filing gate."""
    from enginelib import advisor
    _seed(tmp_path, monkeypatch)  # sets CLAUDE_PROJECT_DIR to tmp_path/project
    # _seed() points CONCLAVE_ENGINE_ROOT at a bare seed dir with no
    # forge-operations/references/templates tree, but advisor.create needs the
    # REAL agent-frontmatter.md template (via templates_dir()) and roster
    # resolution. Unset it so both fall back to the real engine location —
    # mirrors tests/cmd/test_advisor_create.py, which never sets
    # CONCLAVE_ENGINE_ROOT either. project-agents discovery still runs off
    # CLAUDE_PROJECT_DIR (set by _seed above), unaffected by this delenv.
    monkeypatch.delenv("CONCLAVE_ENGINE_ROOT", raising=False)
    advisor.create(advisor.AdvisorOpts(id="testx", role="Test Advisor", color="blue"))
    assert is_canonical_advisor("testx") is True


# ---------------------------------------------------------------------------
# AC5: create -> router round-trip. advisor.create must also scaffold the
# project-side /conclave-<id> invocation router.
# ---------------------------------------------------------------------------

def test_create_also_scaffolds_router(tmp_path, monkeypatch):
    """AC5: a freshly created flat advisor gets a /conclave-<id> router skill."""
    from enginelib import advisor
    _seed(tmp_path, monkeypatch)  # sets CLAUDE_PROJECT_DIR to tmp_path/project
    # See test_created_advisor_is_canonical_and_files above — advisor.create needs
    # the REAL agent-frontmatter.md + advisor-router.md templates via templates_dir().
    monkeypatch.delenv("CONCLAVE_ENGINE_ROOT", raising=False)
    result = advisor.create(advisor.AdvisorOpts(id="iris", role="Design Advisor", color="violet"))
    router_skill = tmp_path / "project" / ".claude" / "skills" / "conclave-iris" / "SKILL.md"
    assert router_skill.is_file()
    assert "conclave-iris" in router_skill.read_text()
    assert result["router"] == str(router_skill)


# ---------------------------------------------------------------------------
# #75 — advisor.create rendered the WRONG persona template and never wrote the
# briefing stub, so hire.md's own documented validation failed on every hire.
# ---------------------------------------------------------------------------

# The four axes hire.md §3a.5 greps for; the generic templates/personality.md
# (Voice / Thinking style / Boundaries / Relationship to product) scores 0 of 4.
_VOICE_AXES = (
    "Domain Vocabulary",
    "Characteristic Questions",
    "Analytical Framework",
    "Metaphor",
)


def _create_into(tmp_path, monkeypatch, id_="vega"):
    """Run advisor.create with a DATA root as well as a project root."""
    from enginelib import advisor
    _seed(tmp_path, monkeypatch)
    monkeypatch.delenv("CONCLAVE_ENGINE_ROOT", raising=False)
    data_root = tmp_path / "data"
    (data_root / "agent-memory" / "advisors" / "briefings").mkdir(parents=True)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(data_root))
    advisor.create(advisor.AdvisorOpts(id=id_, role="Vault Advisor", color="cyan"))
    return data_root


def test_create_renders_the_four_axis_voice_template(tmp_path, monkeypatch):
    """§3a.5 validates the persona by grepping for 4 axes; create must satisfy it."""
    _create_into(tmp_path, monkeypatch)
    persona = (
        tmp_path / "project" / ".claude" / "skills" / "conclave-vega"
        / "memory" / "personality.md"
    ).read_text()

    missing = [axis for axis in _VOICE_AXES if axis not in persona]
    assert not missing, f"persona is missing the §3a.5 axes: {missing}"


def test_create_writes_the_awaiting_first_launch_briefing_stub(tmp_path, monkeypatch):
    """hire.md's Post-hire step asserts this sentinel exists; nothing wrote it."""
    data_root = _create_into(tmp_path, monkeypatch)
    stub = data_root / "agent-memory" / "advisors" / "briefings" / "vega.md"

    assert stub.is_file(), "no briefing stub was written"
    assert "AWAITING_FIRST_LAUNCH" in stub.read_text()


def test_briefing_stub_substitutes_the_advisor_id(tmp_path, monkeypatch):
    """A stub still carrying ${ID} would ship the placeholder to the operator."""
    data_root = _create_into(tmp_path, monkeypatch)
    text = (data_root / "agent-memory" / "advisors" / "briefings" / "vega.md").read_text()

    assert "vega" in text
    assert "${ID}" not in text
