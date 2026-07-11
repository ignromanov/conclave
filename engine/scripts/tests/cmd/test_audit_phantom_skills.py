"""tests/cmd/test_audit_phantom_skills.py — integration tests for `engine audit phantom-skills`.

Hermeticity strategy: set CONCLAVE_ENGINE_ROOT so paths.skills_dir() resolves to
tmp_path/engine/skills (used by the audit scan AND by skill.verify() project-local
lookup). Block global/cache with empty-dir env vars so verify() never reaches ~/.claude.
"""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine


def _setup_skills(tmp_path: Path) -> tuple[Path, dict]:
    """Return (skills_dir, env) for a hermetic tmp engine root."""
    engine_root = tmp_path / "engine"
    skills = engine_root / "skills"
    skills.mkdir(parents=True)
    env = {
        "CONCLAVE_ENGINE_ROOT": str(engine_root),
        "CONCLAVE_GLOBAL_SKILLS_DIR": str(tmp_path / "global"),
        "CLAUDE_PLUGINS_CACHE": str(tmp_path / "cache"),
    }
    return skills, env


def test_phantom_detected(tmp_path):
    """An advisor referencing a nonexistent skill emits WARN line and exits 0."""
    skills, env = _setup_skills(tmp_path)
    advisor = skills / "team._fixture"
    advisor.mkdir()
    (advisor / "SKILL.md").write_text(
        "---\nname: team._fixture\n---\n\n"
        "- `definitely-nonexistent-fixture-skill-xyz`\n"
    )

    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)

    assert r.returncode == 0
    assert "phantom skill: definitely-nonexistent-fixture-skill-xyz" in r.stdout


def test_real_skill_not_flagged(tmp_path):
    """An advisor referencing a skill that exists locally is NOT flagged."""
    skills, env = _setup_skills(tmp_path)
    # Create the real skill in the same skills dir
    (skills / "find-skills").mkdir()
    (skills / "find-skills" / "SKILL.md").write_text("# find-skills\n")
    # Advisor that references it
    (skills / "team.realadv").mkdir()
    (skills / "team.realadv" / "SKILL.md").write_text(
        "---\nname: team.realadv\n---\n\n"
        "- `find-skills`\n"
    )

    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)

    assert r.returncode == 0
    assert "phantom skill: find-skills" not in r.stdout


def test_conclave_prefix_advisor_scanned(tmp_path):
    """#54: a current-layout conclave-<id> advisor is scanned for phantom refs."""
    skills, env = _setup_skills(tmp_path)
    adv = skills / "conclave-newadv"
    adv.mkdir()
    (adv / "SKILL.md").write_text(
        "---\nname: newadv\n---\n\n"
        "- `definitely-nonexistent-fixture-skill-xyz`\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: definitely-nonexistent-fixture-skill-xyz" in r.stdout


def test_conclave_prefix_lifecycle_skipped(tmp_path):
    """#54: conclave-forge (lifecycle) is skipped by bare id."""
    skills, env = _setup_skills(tmp_path)
    (skills / "conclave-forge").mkdir()
    (skills / "conclave-forge" / "SKILL.md").write_text(
        "---\nname: forge\n---\n\n"
        "- `definitely-nonexistent-fixture-skill-xyz`\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill" not in r.stdout


def test_lifecycle_skill_skipped(tmp_path):
    """team.forge referencing a phantom is skipped (lifecycle advisor)."""
    skills, env = _setup_skills(tmp_path)
    (skills / "team.forge").mkdir()
    (skills / "team.forge" / "SKILL.md").write_text(
        "---\nname: team.forge\n---\n\n"
        "- `definitely-nonexistent-fixture-skill-xyz`\n"
    )

    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)

    assert r.returncode == 0
    assert "phantom skill" not in r.stdout


# ── #3: widened fileset (advisor-authored surface) ──────────────────────────

def test_personality_md_scanned(tmp_path):
    """#3: a phantom ref in memory/personality.md is caught (widen beyond SKILL.md)."""
    skills, env = _setup_skills(tmp_path)
    adv = skills / "conclave-widened"
    (adv / "memory").mkdir(parents=True)
    (adv / "SKILL.md").write_text("---\nname: widened\n---\n\nrouter\n")
    (adv / "memory" / "personality.md").write_text(
        "Tier-1:\n- `definitely-nonexistent-fixture-skill-xyz` — desc\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: definitely-nonexistent-fixture-skill-xyz" in r.stdout


def test_references_md_scanned(tmp_path):
    """#3: a phantom ref under references/**/*.md is caught."""
    skills, env = _setup_skills(tmp_path)
    adv = skills / "conclave-refadv"
    (adv / "references").mkdir(parents=True)
    (adv / "SKILL.md").write_text("---\nname: refadv\n---\n\nrouter\n")
    (adv / "references" / "toolbox.md").write_text(
        "- `definitely-nonexistent-fixture-skill-xyz` — desc\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: definitely-nonexistent-fixture-skill-xyz" in r.stdout


def test_agent_def_scanned(tmp_path):
    """#3 (agent-awareness): a phantom ref in .claude/agents/*.md is caught."""
    skills, env = _setup_skills(tmp_path)
    # agents dir is derived as skills_dir.parent / "agents"
    agents = skills.parent / "agents"
    agents.mkdir(parents=True)
    (agents / "someagent.md").write_text(
        "---\nname: someagent\n---\n\n"
        "Load the `definitely-nonexistent-fixture-skill-xyz` skill.\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: definitely-nonexistent-fixture-skill-xyz" in r.stdout


def test_dual_layout_memory_union_scanned(tmp_path):
    """#3: router under conclave-<id> but personality under team.<id>/memory — both scanned."""
    skills, env = _setup_skills(tmp_path)
    (skills / "conclave-splitadv").mkdir()
    (skills / "conclave-splitadv" / "SKILL.md").write_text(
        "---\nname: splitadv\n---\n\nthin router\n"
    )
    legacy_mem = skills / "team.splitadv" / "memory"
    legacy_mem.mkdir(parents=True)
    (legacy_mem / "personality.md").write_text(
        "Tier-1:\n- `definitely-nonexistent-fixture-skill-xyz` — desc\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: definitely-nonexistent-fixture-skill-xyz" in r.stdout


# ── #3: invocation-context heuristic (no false positives) ───────────────────

def test_self_reference_not_flagged(tmp_path):
    """#3 (D3 FP): `advisor \\`sage-cto\\`` — a bare advisor id with no invocation cue — is NOT a skill."""
    skills, env = _setup_skills(tmp_path)
    adv = skills / "conclave-sage-cto"
    adv.mkdir()
    (adv / "SKILL.md").write_text(
        "---\nname: sage-cto\n---\n\n"
        "Then follow the full protocol as advisor `sage-cto`.\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: sage-cto" not in r.stdout


def test_bare_noun_without_cue_not_flagged(tmp_path):
    """#3: a bare kebab domain noun in prose (no cue, not an advisor) is NOT flagged."""
    skills, env = _setup_skills(tmp_path)
    adv = skills / "conclave-proseadv"
    adv.mkdir()
    (adv / "SKILL.md").write_text(
        "---\nname: proseadv\n---\n\n"
        "Writes are contained under the `run-log` directory during pytest.\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: run-log" not in r.stdout


def test_toolbox_bullet_phantom_flagged(tmp_path):
    """#3: a bare-kebab skill listed as a Toolbox bullet (invocation context) IS flagged."""
    skills, env = _setup_skills(tmp_path)
    adv = skills / "conclave-tooladv"
    (adv / "memory").mkdir(parents=True)
    (adv / "SKILL.md").write_text("---\nname: tooladv\n---\n\nrouter\n")
    (adv / "memory" / "personality.md").write_text(
        "Tier-2 (frequent):\n- `ghost-cli-fixture` (some description)\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: ghost-cli-fixture" in r.stdout


def test_namespaced_phantom_flagged(tmp_path):
    """#3: a namespaced token (high-confidence shape) is always verified — phantom flagged."""
    skills, env = _setup_skills(tmp_path)
    adv = skills / "conclave-nsadv"
    (adv / "memory").mkdir(parents=True)
    (adv / "SKILL.md").write_text("---\nname: nsadv\n---\n\nrouter\n")
    (adv / "memory" / "personality.md").write_text(
        "Prose that merely mentions `plugin:ghostxyz-fixture` inline.\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: plugin:ghostxyz-fixture" in r.stdout


def test_cross_advisor_ref_resolved_against_roster(tmp_path):
    """#3: `team.<id>` resolves against the advisor roster, not skill.verify.

    A ref to a nonexistent advisor is flagged; a ref to a real hired advisor is not.
    """
    skills, env = _setup_skills(tmp_path)
    # real advisor in the roster
    (skills / "conclave-realadv").mkdir()
    (skills / "conclave-realadv" / "SKILL.md").write_text("---\nname: realadv\n---\n\nx\n")
    # referrer names both a real and a ghost advisor
    ref = skills / "conclave-referrer"
    ref.mkdir()
    (ref / "SKILL.md").write_text(
        "---\nname: referrer\n---\n\n"
        "Redirect to `team.realadv`; never to `team.ghostadvisor`.\n"
    )
    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)
    assert r.returncode == 0
    assert "phantom skill: team.ghostadvisor" in r.stdout
    assert "phantom skill: team.realadv" not in r.stdout
