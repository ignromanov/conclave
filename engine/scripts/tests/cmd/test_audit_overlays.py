"""tests/cmd/test_audit_overlays.py — integration tests for `engine audit overlays`.

Hermeticity strategy: BARE tmp_path (NOT ai_root fixture). Two env seams:
  CONCLAVE_AI_ROOT    → skills_dir = <tmp_ai>/.claude/skills
  CONCLAVE_ENGINE_ROOT → contracts_dir = <tmp_engine>/contracts
"""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine


def _setup(tmp_path: Path) -> tuple[Path, Path, dict]:
    """Return (skills_dir, contracts_dir, env) for hermetic tmp roots."""
    tmp_ai = tmp_path / "ai"
    tmp_engine = tmp_path / "engine"
    skills = tmp_ai / ".claude" / "skills"
    contracts = tmp_engine / "contracts"
    skills.mkdir(parents=True)
    contracts.mkdir(parents=True)
    env = {
        "CONCLAVE_AI_ROOT": str(tmp_ai),
        "CONCLAVE_ENGINE_ROOT": str(tmp_engine),
    }
    return skills, contracts, env


def test_clean(tmp_path):
    """Overlay with matching version + SKILL.md mentioning contract → no output, exit 0."""
    skills, contracts, env = _setup(tmp_path)
    adv = "team.alpha"
    contract = "session-lifecycle"

    (skills / adv / "contracts").mkdir(parents=True)
    (skills / adv / "contracts" / f"{contract}.md").write_text(
        "overrides-base-version: 1\n", encoding="utf-8"
    )
    (contracts / f"{contract}.md").write_text("version: 1\n", encoding="utf-8")
    (skills / adv / "SKILL.md").write_text(
        f"# {adv}\n\n## Contract Overrides\n- {contract}\n", encoding="utf-8"
    )

    r = run_engine("audit", "overlays", env=env)

    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_no_base(tmp_path):
    """Overlay without a matching base file emits WARN with exact message, exit 0."""
    skills, contracts, env = _setup(tmp_path)
    adv = "team.beta"
    contract = "session-lifecycle"

    (skills / adv / "contracts").mkdir(parents=True)
    (skills / adv / "contracts" / f"{contract}.md").write_text(
        "overrides-base-version: 1\n", encoding="utf-8"
    )
    # intentionally no base file

    r = run_engine("audit", "overlays", env=env)

    assert r.returncode == 0
    assert f"WARN: {adv} overlay {contract} has no base in team.forge/contracts/" in r.stdout


def test_version_mismatch(tmp_path):
    """Overlay version mismatch emits WARN with literal ≠ char, exit 0."""
    skills, contracts, env = _setup(tmp_path)
    adv = "team.gamma"
    contract = "session-lifecycle"

    (skills / adv / "contracts").mkdir(parents=True)
    (skills / adv / "contracts" / f"{contract}.md").write_text(
        "overrides-base-version: 1\n", encoding="utf-8"
    )
    (contracts / f"{contract}.md").write_text("version: 2\n", encoding="utf-8")

    r = run_engine("audit", "overlays", env=env)

    assert r.returncode == 0
    assert f"WARN: {adv} overlay {contract} base-version 1 ≠ current 2" in r.stdout


def test_not_declared(tmp_path):
    """Overlay undeclared in SKILL.md emits INFO line, exit 0."""
    skills, contracts, env = _setup(tmp_path)
    adv = "team.delta"
    contract = "session-lifecycle"

    (skills / adv / "contracts").mkdir(parents=True)
    (skills / adv / "contracts" / f"{contract}.md").write_text(
        "overrides-base-version: 1\n", encoding="utf-8"
    )
    (contracts / f"{contract}.md").write_text("version: 1\n", encoding="utf-8")
    (skills / adv / "SKILL.md").write_text(
        "# team.delta\n\nSome skill with no contract references.\n", encoding="utf-8"
    )

    r = run_engine("audit", "overlays", env=env)

    assert r.returncode == 0
    assert (
        f"INFO: {adv} overlay {contract} not declared in SKILL.md ## Contract Overrides"
        in r.stdout
    )


def test_forge_excluded(tmp_path):
    """team.forge overlays are NOT scanned even without a base file → no output, exit 0."""
    skills, contracts, env = _setup(tmp_path)

    (skills / "team.forge" / "contracts").mkdir(parents=True)
    (skills / "team.forge" / "contracts" / "some-contract.md").write_text(
        "overrides-base-version: 1\n", encoding="utf-8"
    )
    # intentionally no base file — would WARN if scanned

    r = run_engine("audit", "overlays", env=env)

    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_conclave_prefix_overlay_scanned(tmp_path):
    """#54: an overlay under a current-layout conclave-<id> dir is scanned; the display
    keeps the full dir-name (conclave-eps)."""
    skills, contracts, env = _setup(tmp_path)
    adv = "conclave-eps"
    contract = "session-lifecycle"
    (skills / adv / "contracts").mkdir(parents=True)
    (skills / adv / "contracts" / f"{contract}.md").write_text(
        "overrides-base-version: 1\n", encoding="utf-8"
    )
    # no base → WARN
    r = run_engine("audit", "overlays", env=env)
    assert r.returncode == 0
    assert f"WARN: {adv} overlay {contract} has no base in team.forge/contracts/" in r.stdout


def test_conclave_forge_excluded(tmp_path):
    """#54: conclave-forge (current-layout meta) overlays are excluded by bare id."""
    skills, contracts, env = _setup(tmp_path)
    (skills / "conclave-forge" / "contracts").mkdir(parents=True)
    (skills / "conclave-forge" / "contracts" / "some-contract.md").write_text(
        "overrides-base-version: 1\n", encoding="utf-8"
    )
    r = run_engine("audit", "overlays", env=env)
    assert r.returncode == 0
    assert r.stdout.strip() == ""
