"""tests/cmd/test_model_bump.py — integration tests for `engine model bump`.

Uses the ai_root fixture so CONCLAVE_ENGINE_ROOT is set and the real skills tree
(including team.forge/references/agent-model-version.md) is available.

Lifecycle list faithfulness: the engine uses 7-entry lifecycle list from the original
.sh (team.start/processing/done/handoff/forge/hire/retro), not the canonical 9-entry
set used elsewhere. The tests for --all assert only the seeded non-lifecycle advisors
appear, verifying lifecycle exclusion without depending on the exact 7-vs-9 delta.
"""
from __future__ import annotations

import os
from pathlib import Path

from tests.cmd.helpers import run_engine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORGE_FM = """\
---
name: conclave-{name}
forge:
  model-version: 0.0.0
  hired-by: forge
  last-evolve: 0.0.0
---
stub
"""

_NO_FORGE_FM = """\
---
name: conclave-{name}
---
stub
"""


def _project_skills() -> Path:
    """Project-side skills root the bump adapter now targets (#55):
    CONCLAVE_AI_ROOT/.claude/skills (project_skills_dir() in the test layout)."""
    return Path(os.environ["CONCLAVE_AI_ROOT"]) / ".claude" / "skills"


def _seed(name: str, *, forge: bool = True) -> Path:
    """Write a SKILL.md under <project>/.claude/skills/conclave-<name>/ (#55)."""
    skill_dir = _project_skills() / f"conclave-{name}"
    skill_dir.mkdir(parents=True, exist_ok=True)
    template = _FORGE_FM if forge else _NO_FORGE_FM
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(template.format(name=name))
    return skill_md


def _run(*args: str, engine_root: Path) -> subprocess.CompletedProcess:  # noqa: F821
    return run_engine("model", "bump", *args, env={"CONCLAVE_ENGINE_ROOT": str(engine_root)})


def _read_field(skill_md: Path, field: str) -> str | None:
    """Read a `  field: value` line from inside a forge: block."""
    in_forge = False
    for line in skill_md.read_text().splitlines():
        bare = line.strip()
        if line.startswith("forge:"):
            in_forge = True
            continue
        if in_forge and bare.startswith(f"{field}:"):
            return bare.split(":", 1)[1].strip()
        if in_forge and line and line[0] not in (" ", "\t") and not line.startswith("forge:"):
            break
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bump_advisor_model_version_only(ai_root):
    """--advisor bumps model-version only; hired-by/last-evolve unchanged."""
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    skill_md = _seed("alpha")

    r = _run("--advisor", "alpha", engine_root=engine_root)

    assert r.returncode == 0
    assert "bumped: alpha" in r.stdout

    # model-version updated to current standard
    mv = _read_field(skill_md, "model-version")
    assert mv is not None and mv != "0.0.0", f"model-version not updated: {mv!r}"

    # hired-by (actor) and last-evolve must be UNCHANGED (no --set-all)
    assert _read_field(skill_md, "hired-by") == "forge"
    assert _read_field(skill_md, "last-evolve") == "0.0.0"


def test_bump_advisor_set_all(ai_root):
    """--advisor --set-all stamps model-version + last-evolve; hired-by (actor) preserved."""
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    skill_md = _seed("beta")

    r = _run("--advisor", "beta", "--set-all", engine_root=engine_root)

    assert r.returncode == 0
    assert "bumped: beta" in r.stdout

    # Version-carrying fields stamped to the current standard (non-zero)
    mv = _read_field(skill_md, "model-version")
    le = _read_field(skill_md, "last-evolve")
    assert mv == le, f"version fields not equal: mv={mv!r} le={le!r}"
    assert mv != "0.0.0"

    # hired-by is an actor — must NOT be version-stamped (feedback 240857/i1)
    assert _read_field(skill_md, "hired-by") == "forge"


def test_bump_advisor_dry_run(ai_root):
    """--advisor --dry-run prints would-bump; file is unchanged."""
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    skill_md = _seed("gamma")
    original = skill_md.read_text()

    r = _run("--advisor", "gamma", "--dry-run", engine_root=engine_root)

    assert r.returncode == 0
    assert "would bump gamma model-version" in r.stdout
    # File must not have changed
    assert skill_md.read_text() == original


def test_bump_advisor_no_forge_block(ai_root):
    """Advisor with no forge: block → SKIP on stderr; file untouched; exit 0."""
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    skill_md = _seed("delta", forge=False)
    original = skill_md.read_text()

    r = _run("--advisor", "delta", engine_root=engine_root)

    assert r.returncode == 0
    assert "SKIP" in r.stderr and "forge:" in r.stderr
    assert skill_md.read_text() == original


def test_bump_all_dry_run_mentions_model_version(ai_root):
    """--all --dry-run: output mentions model-version (ports the original .test.sh case)."""
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    _seed("epsilon")

    r = _run("--all", "--dry-run", engine_root=engine_root)

    assert r.returncode == 0
    assert "model-version" in r.stdout


def test_bump_all_excludes_lifecycle(ai_root):
    """--all: lifecycle skills (e.g. team.forge) do not appear in would-bump output."""
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    _seed("zeta")

    r = _run("--all", "--dry-run", engine_root=engine_root)

    assert r.returncode == 0
    # forge is a lifecycle id — excluded regardless of prefix; the seeded advisor is not.
    bumped_lines = [ln for ln in r.stdout.splitlines() if "would bump" in ln]
    bumped_names = [ln.split("would bump ", 1)[1].split()[0] for ln in bumped_lines]
    assert "forge" not in bumped_names, f"forge must be excluded; got {bumped_names}"
    assert "zeta" in bumped_names, f"seeded advisor missing from output; got {bumped_names}"


def test_bump_neither_flag_exits_1(ai_root):
    """No --advisor or --all → exit 1 with usage on stderr."""
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])

    r = _run(engine_root=engine_root)

    assert r.returncode == 1
    assert "usage" in r.stderr.lower()


def test_bump_advisor_missing_skill_md(ai_root):
    """--advisor for a dir without SKILL.md → exit 0 and 'missing:' on stderr."""
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    # Create the conclave-eta directory but deliberately omit SKILL.md
    skill_dir = _project_skills() / "conclave-eta"
    skill_dir.mkdir(parents=True, exist_ok=True)

    r = _run("--advisor", "eta", engine_root=engine_root)

    assert r.returncode == 0
    assert "missing:" in r.stderr
