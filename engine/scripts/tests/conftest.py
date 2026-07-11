"""conftest.py — shared pytest fixtures for Wave-3 engine <noun> <verb> cmd tests.

Replaces engine/scripts/tests/helpers/fixtures.bash. Parity contract:
  - ai_root       ↔  fixture_setup   (tmp DATA+CODE tree + env vars)
  - seed_advisors ↔  _seed_advisors  (dual-location SKILL.md stubs)

Extensions vs brief (matching fixtures.bash semantics):
  1. Real skills/ tree copied into fake engine root (forge templates resolve).
  2. VOIDPAY_AI_ROOT set alongside CONCLAVE_AI_ROOT (roster.py fallback).
  3. .ai/.claude/skills/team.forge/scripts/ dir created (scripts that walk DATA root).
  4. seed_advisors writes stubs in both engine/skills/ and ai/.claude/skills/.
  5. ai_root auto-seeds canonical roster: dev kai-cto nexus-ceo quorum shade-ciso spark-cmo.
  6. SKILL.md content: "stub for tests" (matches fixtures.bash printf string).
"""
import os
import shutil
from pathlib import Path

import pytest

# Real engine root: this file lives at engine/scripts/tests/conftest.py
# parents[0]=tests  parents[1]=scripts  parents[2]=engine
_REAL_ENGINE_ROOT = Path(__file__).resolve().parents[2]

# Canonical advisor names auto-seeded by fixture_setup in fixtures.bash.
_CANONICAL_ADVISORS = ("dev", "kai-cto", "nexus-ceo", "quorum", "shade-ciso", "spark-cmo")

# Hermeticity: clear ambient instance-root env vars at conftest IMPORT (before test
# collection) so `@skipif(not CONCLAVE_AI_ROOT)` gates (e.g. _NEEDS_INSTANCE) evaluate
# against a clean env and skip live-instance smoke tests, instead of running them
# against the real .conclave tree exported by the SessionStart hook. Per-test isolation
# is reinforced by the _hermetic_instance_env autouse fixture below. CONCLAVE_ENGINE_ROOT
# (CODE root) is intentionally left set. (feedback f69060/i1, 240857/i2)
#
# The SessionStart hook exports CONCLAVE_AI_ROOT UNCONDITIONALLY, so it can't double as
# the "run live-instance tests" signal. Opt in explicitly with CONCLAVE_TEST_LIVE=1
# (keep CONCLAVE_AI_ROOT set) to run the _NEEDS_INSTANCE smoke tests against a real tree.
_LIVE_TESTS = os.environ.get("CONCLAVE_TEST_LIVE")
_INSTANCE_ROOT_VARS = ("CONCLAVE_AI_ROOT", "VOIDPAY_AI_ROOT", "CLAUDE_PROJECT_DIR")
if not _LIVE_TESTS:
    for _var in _INSTANCE_ROOT_VARS:
        os.environ.pop(_var, None)


def _write_skill_stubs(ai_root: Path, engine_root: Path, *names: str) -> None:
    """Create team.<name>/SKILL.md stubs in both anchor locations, plus a flat
    .claude/agents/<name>.md agent-def so registry-driven discovery
    (enginelib.advisors.known_advisors) sees the roster on the post-098 layout.

    Mirrors _seed_advisors from fixtures.bash:
      engine_root/skills/team.<name>/SKILL.md  — CONCLAVE_ENGINE_ROOT anchor
      ai_root/.claude/skills/team.<name>/SKILL.md — DATA root anchor
      ai_root/.claude/agents/<name>.md — flat agent registry (#47 discovery)
    """
    agents_dir = ai_root / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        content = f"---\nname: team.{name}\n---\nstub for tests\n"
        for base in (
            engine_root / "skills",
            ai_root / ".claude" / "skills",
        ):
            skill_dir = base / f"team.{name}"
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                skill_md.write_text(content)
        agent_md = agents_dir / f"{name}.md"
        if not agent_md.exists():
            agent_md.write_text(f"---\nname: {name}\n---\nstub for tests\n")


@pytest.fixture(autouse=True)
def _contain_run_log(tmp_path, monkeypatch):
    """Route every test's run-log write into tmp so the append-on-exit
    observability primitive never pollutes the real repo run-log (#53). Points at
    the same relative path bare-tmp_path read-tests expect, so those stay green;
    tests that leave CONCLAVE_AI_ROOT unset (the polluters) are now contained."""
    monkeypatch.setenv("CONCLAVE_RUN_LOG_DIR", str(tmp_path / "agent-memory" / "run-log"))


@pytest.fixture(autouse=True)
def _hermetic_instance_env(monkeypatch):
    """Clear ambient instance-root env vars so the suite is hermetic by default.

    The SessionStart hook exports CONCLAVE_AI_ROOT (and consumers may export
    CLAUDE_PROJECT_DIR / VOIDPAY_AI_ROOT). Left set, they steer repo_root() and
    every registry resolver at the LIVE instance, so path/registry tests read the
    real .conclave tree instead of their own fixture — inflating the baseline and
    masking regressions (feedback f69060/i1, 240857/i2). Tests that need an
    instance root set it explicitly (e.g. the `ai_root` fixture via monkeypatch,
    which runs after this autouse clear). CONCLAVE_ENGINE_ROOT (CODE root) is left
    untouched — it is not an instance root. Skipped when CONCLAVE_TEST_LIVE=1."""
    if _LIVE_TESTS:
        return
    for var in _INSTANCE_ROOT_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def ai_root(tmp_path, monkeypatch):
    """Hermetic DATA+CODE tree. Mirrors fixture_setup from fixtures.bash.

    Layout::

        tmp_path/
          .ai/                        ← CONCLAVE_AI_ROOT + VOIDPAY_AI_ROOT
            agent-memory/advisors/{briefings,sessions,decisions,mentions}/
            .claude/skills/team.forge/scripts/
            .claude/skills/team.<canonical_advisor>/SKILL.md  (×6 auto-seeded)
          engine/                     ← CONCLAVE_ENGINE_ROOT
            skills/   ← real engine/skills/ copied in (forge templates etc.)
              team.<canonical_advisor>/SKILL.md  (×6 auto-seeded)
    """
    root = tmp_path / ".ai"

    # 1. Agent-memory advisor subdirs
    #    mirrors: mkdir -p $FIXTURE_AI_ROOT/agent-memory/advisors/{briefings,sessions,decisions,mentions}
    for sub in ("briefings", "sessions", "decisions", "mentions"):
        (root / "agent-memory" / "advisors" / sub).mkdir(parents=True, exist_ok=True)

    # 2. forge/scripts dir in ai root
    #    mirrors: mkdir -p $FIXTURE_AI_ROOT/.claude/skills/team.forge/scripts
    (root / ".claude" / "skills" / "team.forge" / "scripts").mkdir(parents=True, exist_ok=True)

    # 3. Env: DATA roots (VOIDPAY_AI_ROOT is the roster.py fallback)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    monkeypatch.setenv("VOIDPAY_AI_ROOT", str(root))

    # 4. Fake engine root — copy real skills/ so advisor SKILL.md stubs resolve
    #    mirrors: cp -r "$_real_engine_root/skills" "$FIXTURE_ENGINE_ROOT/"
    engine_root = tmp_path / "engine"
    real_skills = _REAL_ENGINE_ROOT / "skills"
    if real_skills.is_dir():
        shutil.copytree(real_skills, engine_root / "skills")
    else:
        (engine_root / "skills").mkdir(parents=True)
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine_root))

    # 4b. Forge references/templates are CODE at repo_root/skills/forge-operations
    #     (sibling of engine/). engine_root().parent == tmp_path, so mirror the
    #     real sibling layout there — forge_references_dir()/forge_templates_dir()
    #     resolve to engine_root().parent/skills/forge-operations/references[/templates].
    real_forge_ops = _REAL_ENGINE_ROOT.parent / "skills" / "forge-operations"
    if real_forge_ops.is_dir():
        shutil.copytree(real_forge_ops, tmp_path / "skills" / "forge-operations")

    # 5. Auto-seed canonical advisor roster
    #    mirrors: _seed_advisors dev kai-cto nexus-ceo quorum shade-ciso spark-cmo
    _write_skill_stubs(root, engine_root, *_CANONICAL_ADVISORS)

    return root


@pytest.fixture
def seed_advisors(ai_root, monkeypatch):
    """Return a callable that seeds additional advisor stubs beyond the canonical set.

    Usage::

        def test_foo(seed_advisors):
            seed_advisors("my-advisor", "other-advisor")

    Mirrors _seed_advisors from fixtures.bash: writes SKILL.md into both
    CONCLAVE_ENGINE_ROOT/skills/ and CONCLAVE_AI_ROOT/.claude/skills/.
    """
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])

    def _factory(*names: str) -> None:
        _write_skill_stubs(ai_root, engine_root, *names)

    return _factory
