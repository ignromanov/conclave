"""tests/cmd/test_audit_versions.py — integration tests for `engine audit versions`.

Hermetic: bare tmp_path (NOT ai_root fixture). Skills tree injected via --skills-dir.
Standard version file at tmp_skills/team.forge/references/agent-model-version.md.
"""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine

_STANDARD_MD = "## Current standard: 2.1\n"


def _make_standard(skills: Path) -> None:
    ref_dir = skills / "team.forge" / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / "agent-model-version.md").write_text(_STANDARD_MD, encoding="utf-8")


def _make_advisor(skills: Path, name: str, content: str) -> None:
    d = skills / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(content, encoding="utf-8")


def _skill(model_version: str) -> str:
    return (
        "---\n"
        "name: team.adv\n"
        "forge:\n"
        f"  model-version: {model_version}\n"
        "---\n"
        "# body\n"
    )


def _run(tmp_skills: Path, tmp: Path):
    return run_engine(
        "audit", "versions",
        "--skills-dir", str(tmp_skills),
        env={"CONCLAVE_AI_ROOT": str(tmp)},
    )


# 1. Standard header printed + OK for matching version → exit 0
def test_standard_header_and_ok(tmp_path):
    skills = tmp_path / "skills"
    _make_standard(skills)
    _make_advisor(skills, "team.adv", _skill("2.1"))
    r = _run(skills, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "standard: 2.1" in r.stdout
    assert "OK: team.adv at 2.1" in r.stdout


# 2. MINOR gap → WARN, exit 2
def test_minor_gap_warn(tmp_path):
    skills = tmp_path / "skills"
    _make_standard(skills)
    _make_advisor(skills, "team.adv", _skill("2.0"))
    r = _run(skills, tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "WARN: team.adv at 2.0 (MINOR gap vs 2.1)" in r.stdout


# 3. MAJOR gap → CRIT, exit 1
def test_major_gap_crit(tmp_path):
    skills = tmp_path / "skills"
    _make_standard(skills)
    _make_advisor(skills, "team.adv", _skill("1.5"))
    r = _run(skills, tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "CRIT: team.adv at 1.5 (MAJOR gap vs 2.1)" in r.stdout


# 4. No forge.model-version stamp → CRIT, exit 1
def test_no_stamp_crit(tmp_path):
    skills = tmp_path / "skills"
    _make_standard(skills)
    no_stamp = "---\nname: team.adv\n---\n# body\n"
    _make_advisor(skills, "team.adv", no_stamp)
    r = _run(skills, tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "CRIT: team.adv has no forge.model-version stamp" in r.stdout


# 5. Lifecycle skill skipped — no OK/WARN/CRIT line for it; standard: still printed; exit 0
def test_lifecycle_skip(tmp_path):
    skills = tmp_path / "skills"
    _make_standard(skills)
    # team.start is in the lifecycle skip set
    _make_advisor(skills, "team.start", _skill("1.0"))
    r = _run(skills, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "standard: 2.1" in r.stdout
    assert "team.start" not in r.stdout


# 5b. #54: a conclave-<id> advisor is discovered and version-checked; the display
#     name keeps the full dir-name (conclave-adv), lifecycle excluded by bare id.
def test_conclave_prefix_advisor_checked(tmp_path):
    skills = tmp_path / "skills"
    _make_standard(skills)
    _make_advisor(skills, "conclave-adv", _skill("1.5"))
    _make_advisor(skills, "conclave-start", _skill("1.0"))  # lifecycle → skip
    r = _run(skills, tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "CRIT: conclave-adv at 1.5 (MAJOR gap vs 2.1)" in r.stdout
    assert "conclave-start" not in r.stdout


# 6. Forge-block scoping: top-level model-version: 9.9 must NOT be read;
#    only the forge: block's indented model-version: 2.1 → OK, exit 0
def test_forge_block_scoping(tmp_path):
    skills = tmp_path / "skills"
    _make_standard(skills)
    scoped = (
        "---\n"
        "name: team.adv\n"
        "model-version: 9.9\n"
        "forge:\n"
        "  model-version: 2.1\n"
        "---\n"
        "# body\n"
    )
    _make_advisor(skills, "team.adv", scoped)
    r = _run(skills, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK: team.adv at 2.1" in r.stdout
    assert "9.9" not in r.stdout


# 7. Default resolution (NO --skills-dir): standard_file must resolve to the REAL
# forge-operations/references/agent-model-version.md (not a dead team.forge path that
# 404s). Proven by asserting the printed "standard:" line is non-empty and matches the
# real file's "## Current standard:" value — before the fix, the default standard_file
# pointed at engine/skills/team.forge/... which no longer exists, so standard_file.is_file()
# would be False and "standard:" would print empty.
def test_default_standard_file_resolves_to_real_forge_operations(tmp_path):
    from enginelib.paths import forge_references_dir

    real_standard = forge_references_dir() / "agent-model-version.md"
    assert real_standard.is_file(), f"fixture assumption broken: {real_standard} missing"
    expected = None
    for line in real_standard.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Current standard:"):
            expected = line.split()[3]
            break
    assert expected, "real agent-model-version.md must have a '## Current standard:' line"

    r = run_engine("audit", "versions", env={"CONCLAVE_AI_ROOT": str(tmp_path)})
    assert r.returncode == 0, r.stdout + r.stderr  # engine/skills has no team.* advisors
    assert f"standard: {expected}" in r.stdout
