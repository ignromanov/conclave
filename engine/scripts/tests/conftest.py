"""conftest.py — shared pytest fixtures for Wave-3 engine <noun> <verb> cmd tests.

Replaces engine/scripts/tests/helpers/fixtures.bash. Parity contract:
  - ai_root       ↔  fixture_setup   (tmp DATA+CODE tree + env vars)
  - seed_advisors ↔  _seed_advisors  (dual-location SKILL.md stubs)

Extensions vs brief (matching fixtures.bash semantics):
  1. Real skills/ tree copied into fake engine root (forge templates resolve).
  2. CONCLAVE_AI_ROOT alone — the retired VOIDPAY_AI_ROOT alias is scrubbed, never set.
  3. .ai/.claude/skills/team.forge/scripts/ dir created (scripts that walk DATA root).
  4. seed_advisors writes stubs in both engine/skills/ and ai/.claude/skills/.
  5. ai_root auto-seeds canonical roster: dev kai-cto nexus-ceo quorum shade-ciso spark-cmo.
  6. SKILL.md content: "stub for tests" (matches fixtures.bash printf string).
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# Real engine root: this file lives at engine/scripts/tests/conftest.py
# parents[0]=tests  parents[1]=scripts  parents[2]=engine
_REAL_ENGINE_ROOT = Path(__file__).resolve().parents[2]

# Canonical advisor names auto-seeded by fixture_setup in fixtures.bash.
_CANONICAL_ADVISORS = ("dev", "kai-cto", "nexus-ceo", "quorum", "shade-ciso", "spark-cmo")

# Hermeticity — the import-time scrub and the per-test `_hermetic_instance_env` fixture —
# lives in the REPO-ROOT conftest.py, not here (GH#239). It was here, and that made it
# reachable only by whatever invocation happened to import this file: the sibling testpath
# `engine/scripts/feedback/tests` has no conftest of its own, so an explicit-path run into
# it collected neither the pop nor the fixture and read the operator's live DATA root.
#
# `_live_instance_root` below stays here and still depends on that fixture by name; pytest
# resolves it from the parent conftest. It is the half of GH#105 that is genuinely specific
# to this directory's markers.
#
# Historical note kept because it explains the shape: the scrub used to be conditional on
# CONCLAVE_TEST_LIVE=1, and that same flag doubled as the "run the live-instance tests"
# signal — one switch for two orthogonal concerns. Entering the live lane therefore disarmed
# hermeticity for the WHOLE suite, reddening four tests that legitimately expect a clean env
# (test_backfill_cli, test_paths::test_repo_root_env_override, test_session_init::
# TestRepoRoot::{test_env_override, test_missing_raises}). That collateral is why the flag
# was never wired into CI, and why 31 gated tests went a month without executing anywhere.

# Opt-in live lane: a path to an instance tree the `live_instance`-marked tests read.
# Deliberately NOT one of the vars above — an ambient CONCLAVE_AI_ROOT export must never
# be able to enable the lane by accident, which is the trap the old flag fell into.
LIVE_INSTANCE_ROOT_VAR = "CONCLAVE_LIVE_INSTANCE_ROOT"


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
def _live_instance_root(request, monkeypatch, _hermetic_instance_env):
    """Point a `live_instance`-marked test at a real instance tree; no-op otherwise.

    Depends on _hermetic_instance_env so it always runs AFTER the clear — the marked
    test gets exactly one instance root, the one named by CONCLAVE_LIVE_INSTANCE_ROOT,
    and every unmarked test keeps the hermetic env. This is the half of GH#105 that was
    missing: the old gate asked "is CONCLAVE_AI_ROOT set?", which is a question about
    whether hermeticity had been switched off, not about whether an instance exists.

    A path that does not exist FAILS rather than skips. A typo'd or moved root would
    otherwise reproduce the original defect exactly — a lane that reports green because
    it silently declined to run."""
    if request.node.get_closest_marker("live_instance") is None:
        return
    raw = os.environ.get(LIVE_INSTANCE_ROOT_VAR)
    if not raw:
        pytest.skip(f"needs a live instance root — set {LIVE_INSTANCE_ROOT_VAR}=<path>")
    root = Path(raw).resolve()
    if not root.is_dir():
        pytest.fail(f"{LIVE_INSTANCE_ROOT_VAR}={raw} is not a directory")
    _refuse_a_dirty_live_root(root)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))


def _uncommitted_tracked_files(root: Path) -> list[str] | None:
    """Tracked files modified under `root`, or None when `root` is not in a git tree.

    `--untracked-files=no` is the whole predicate. A live lane seeded by
    `engine test live` scaffolds a fresh instance that may land INSIDE this checkout, and
    every file in it is untracked; counting those would fail the lane that has nothing to
    lose. What a rewriting run destroys irrecoverably is a tracked file's uncommitted
    edit, and that is what this asks about.
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", str(root)],
        cwd=str(root), capture_output=True, text=True,
    )
    if proc.returncode != 0:            # not a working tree: nothing tracked, nothing to lose
        return None
    return [line[3:] for line in proc.stdout.splitlines() if line.strip()]


def _refuse_a_dirty_live_root(root: Path) -> None:
    """A lane pointed at a real instance runs only against a committed tree (GH#131).

    The live lane is the one place in this suite where tests write to a tree the operator
    is using. It has already cost 34 DATA files: a run in non-hermetic mode rewrote the
    frontmatter of 16 decisions and 18 session records inside a test that names itself a
    safety gate. Committed, that is a diff to inspect and revert; uncommitted, it is gone.

    So the precondition is enforced here rather than written down. GH#131 finding 4 asked
    for a sentence in `session-lifecycle.md` saying a live lane needs a clean DATA tree —
    but the instruction that was missing then would have been read by the same person who
    was about to run the lane anyway, and this week has produced three separate guards
    whose reach depended on somebody remembering them. A check at the fixture runs on
    every invocation of the lane, including the one nobody planned.

    Fails, never skips: a skip is what a green run looks like, which is the defect this
    fixture's own docstring already refuses one paragraph up.
    """
    dirty = _uncommitted_tracked_files(root)
    if not dirty:
        return
    shown = "\n  ".join(dirty[:10])
    more = f"\n  ... and {len(dirty) - 10} more" if len(dirty) > 10 else ""
    pytest.fail(
        f"{LIVE_INSTANCE_ROOT_VAR}={root} has uncommitted changes to {len(dirty)} tracked "
        f"file(s), and the live lane writes to that tree:\n  {shown}{more}\n"
        f"Commit or stash them first. This lane has already rewritten 34 DATA files in one "
        f"run (GH#131); committed, such a run is a diff you can read and revert."
    )


@pytest.fixture
def ai_root(tmp_path, monkeypatch):
    """Hermetic DATA+CODE tree. Mirrors fixture_setup from fixtures.bash.

    Layout::

        tmp_path/
          .ai/                        ← CONCLAVE_AI_ROOT
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

    # 3. Env: the DATA root. Only CONCLAVE_AI_ROOT — this fixture used to set the
    #    retired VOIDPAY_AI_ROOT alias to the same tree as well, which made every
    #    resolver agree by construction: the two repo_root() ports disagreed on five
    #    counts and not one test could reach the disagreement (see
    #    tests/test_root_resolver_agreement.py). A fixture that satisfies every
    #    reader's private convention tests the fixture, not the readers.
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))

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
