"""test_conftest.py — self-tests for conftest.py fixtures.

Verifies that ai_root and seed_advisors build the expected directory tree
and environment variables, mirroring fixtures.bash semantics.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# ai_root fixture
# ---------------------------------------------------------------------------

def test_ai_root_creates_advisor_subdirs(ai_root):
    """ai_root creates the 4 agent-memory/advisors subdirs."""
    base = ai_root / "agent-memory" / "advisors"
    for sub in ("briefings", "sessions", "decisions", "mentions"):
        assert (base / sub).is_dir(), f"missing dir: {sub}"


def test_ai_root_creates_forge_scripts_dir(ai_root):
    """ai_root creates .ai/.claude/skills/team.forge/scripts/ (DATA anchor)."""
    assert (ai_root / ".claude" / "skills" / "team.forge" / "scripts").is_dir()


def test_ai_root_sets_conclave_ai_root(ai_root):
    """CONCLAVE_AI_ROOT points at the .ai tmp root."""
    assert os.environ["CONCLAVE_AI_ROOT"] == str(ai_root)


def test_ai_root_leaves_the_legacy_alias_unset(ai_root):
    """The retired VOIDPAY_AI_ROOT alias must NOT be set alongside CONCLAVE_AI_ROOT.

    It was, for years, pointed at the same tree — which made every DATA-root resolver
    agree by construction and put the divergence between them out of the suite's reach.
    """
    assert "VOIDPAY_AI_ROOT" not in os.environ


def test_ai_root_sets_conclave_engine_root(ai_root):
    """CONCLAVE_ENGINE_ROOT points at the tmp engine/ dir."""
    engine = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    assert engine.is_dir()
    assert (engine / "skills").is_dir()


def test_ai_root_auto_seeds_canonical_advisors(ai_root):
    """ai_root pre-seeds all 6 canonical advisors in both anchor locations."""
    engine = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    for name in ("dev", "kai-cto", "nexus-ceo", "quorum", "shade-ciso", "spark-cmo"):
        assert (engine / "skills" / f"team.{name}" / "SKILL.md").is_file(), (
            f"missing engine SKILL.md for {name}"
        )
        assert (ai_root / ".claude" / "skills" / f"team.{name}" / "SKILL.md").is_file(), (
            f"missing ai-root SKILL.md for {name}"
        )


def test_ai_root_skill_md_content(ai_root):
    """SKILL.md stubs use 'stub for tests' content (matches fixtures.bash)."""
    skill_md = (
        Path(os.environ["CONCLAVE_ENGINE_ROOT"]) / "skills" / "team.nexus-ceo" / "SKILL.md"
    )
    content = skill_md.read_text()
    assert "name: team.nexus-ceo" in content
    assert "stub for tests" in content


# ---------------------------------------------------------------------------
# seed_advisors fixture
# ---------------------------------------------------------------------------

def test_seed_advisors_creates_engine_skill_md(seed_advisors):
    """seed_advisors("test-advisor") creates SKILL.md in engine/skills/."""
    seed_advisors("test-advisor")
    engine = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    assert (engine / "skills" / "team.test-advisor" / "SKILL.md").is_file()


def test_seed_advisors_creates_ai_root_skill_md(ai_root, seed_advisors):
    """seed_advisors("test-advisor") creates SKILL.md in ai_root/.claude/skills/."""
    seed_advisors("test-advisor")
    assert (ai_root / ".claude" / "skills" / "team.test-advisor" / "SKILL.md").is_file()


def test_seed_advisors_idempotent_for_existing(seed_advisors):
    """seed_advisors does not overwrite an already-seeded advisor."""
    seed_advisors("nexus-ceo")  # already auto-seeded by ai_root; should not raise
    engine = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    content = (engine / "skills" / "team.nexus-ceo" / "SKILL.md").read_text()
    assert "stub for tests" in content  # original content preserved


def test_seed_advisors_multiple_names(seed_advisors):
    """seed_advisors accepts multiple names in one call."""
    seed_advisors("alpha", "beta", "gamma")
    engine = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    for name in ("alpha", "beta", "gamma"):
        assert (engine / "skills" / f"team.{name}" / "SKILL.md").is_file()
