"""tests/cmd/test_audit_bloat.py — integration tests for `engine audit bloat`.

Hermetic: bare tmp_path (NOT ai_root). Advisor skills tree injected via --skills-dir;
briefings dir controlled via CONCLAVE_AI_ROOT seam. Forge resources (router SKILL.md,
protocols/, references/aspects/) are CODE at a fixed location (forge-operations/),
independent of --skills-dir; `_run()` isolates them behind a non-existent --forge-dir
fixture by default so real forge-operations content can't leak into unrelated cap
assertions — pass forge_dir= for a synthetic fixture, or real_forge=True to exercise
the real default resolution (see test 8).
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.cmd.helpers import run_engine


def _run(tmp_skills: Path, tmp: Path, forge_dir: Path | None = None, real_forge: bool = False):
    """Run `engine audit bloat`. By default isolates forge resources behind a
    non-existent --forge-dir fixture (tests here care about advisor-skill/briefing
    caps, not the real forge-operations tree). Pass forge_dir= to inject a synthetic
    fixture, or real_forge=True to omit --forge-dir and hit the real default resolution.
    """
    args = ["audit", "bloat", "--skills-dir", str(tmp_skills)]
    if not real_forge:
        args += ["--forge-dir", str(forge_dir if forge_dir is not None else tmp / "no-forge")]
    return run_engine(*args, env={"CONCLAVE_AI_ROOT": str(tmp)})


def _make_skill(skills: Path, name: str, lines: int) -> Path:
    """Create skills/<name>/SKILL.md with exactly `lines` newline characters."""
    d = skills / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_bytes(b"x\n" * lines)
    return p


# 1. CRIT advisor-skill: > 300 newlines (> 2 × 150)
def test_crit_advisor_skill(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "team.adv", 301)
    r = _run(skills, tmp_path)
    assert r.returncode == 1
    assert "CRIT: advisor-skill" in r.stdout
    assert "team.adv/SKILL.md" in r.stdout
    assert "= 301 lines (cap 150)" in r.stdout


# 2. WARN advisor-skill: 151–300 newlines
def test_warn_advisor_skill(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "team.adv", 200)
    r = _run(skills, tmp_path)
    assert r.returncode == 2
    assert "WARN: advisor-skill" in r.stdout
    assert "= 200 lines (cap 150)" in r.stdout


# 3. Under cap: ≤ 150 → clean
def test_under_cap_clean(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "team.adv", 150)
    r = _run(skills, tmp_path)
    assert r.returncode == 0
    assert "0 CRIT, 0 WARN" in r.stdout
    assert "CRIT:" not in r.stdout
    assert "WARN:" not in r.stdout


# 4. Lifecycle skip: team.start not flagged as advisor-skill
def test_lifecycle_skip(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "team.start", 400)
    r = _run(skills, tmp_path)
    assert r.returncode == 0
    assert "CRIT:" not in r.stdout
    assert "WARN:" not in r.stdout


# 5. Bloat-exempt skip: team.quorum not flagged
def test_bloat_exempt_skip(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "team.quorum", 400)
    r = _run(skills, tmp_path)
    assert r.returncode == 0
    assert "CRIT:" not in r.stdout
    assert "WARN:" not in r.stdout


# 5b. #54: a conclave-<id> advisor over cap IS flagged (current-layout discovery)
def test_conclave_prefix_advisor_flagged(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "conclave-adv", 301)
    r = _run(skills, tmp_path)
    assert r.returncode == 1
    assert "CRIT: advisor-skill" in r.stdout
    assert "conclave-adv/SKILL.md" in r.stdout


# 5c. #54: lifecycle + bloat-exempt still skipped under the conclave- prefix
def test_conclave_prefix_lifecycle_and_exempt_skipped(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "conclave-start", 400)   # lifecycle
    _make_skill(skills, "conclave-quorum", 400)  # bloat-exempt
    r = _run(skills, tmp_path)
    assert r.returncode == 0
    assert "CRIT:" not in r.stdout
    assert "WARN:" not in r.stdout


# 6. forge-router cap: forge-operations/SKILL.md, sourced via --forge-dir override
def test_forge_router_cap(tmp_path):
    skills = tmp_path / "skills"
    forge = tmp_path / "forge"
    forge.mkdir(parents=True, exist_ok=True)
    (forge / "SKILL.md").write_bytes(b"x\n" * 400)
    r = _run(skills, tmp_path, forge_dir=forge)
    assert r.returncode == 1
    assert "CRIT: forge-router" in r.stdout
    assert "SKILL.md" in r.stdout
    assert "= 400 lines (cap 150)" in r.stdout
    # Must NOT appear as advisor-skill (only as forge-router)
    assert "advisor-skill" not in r.stdout


# 7. Protocol / aspect / briefing caps
def test_protocol_aspect_briefing_caps(tmp_path):
    skills = tmp_path / "skills"
    forge = tmp_path / "forge"
    # Protocol: cap 220, 441 > 2×220 → CRIT
    proto_dir = forge / "references" / "protocols"
    proto_dir.mkdir(parents=True, exist_ok=True)
    (proto_dir / "x.md").write_bytes(b"x\n" * 441)
    # Aspect: cap 140, 141 > 140 → WARN
    aspects_dir = forge / "references" / "aspects"
    aspects_dir.mkdir(parents=True, exist_ok=True)
    (aspects_dir / "y.md").write_bytes(b"x\n" * 141)
    # Briefing: cap 500, 501 > 500 → WARN
    briefings = tmp_path / "agent-memory" / "advisors" / "briefings"
    briefings.mkdir(parents=True, exist_ok=True)
    (briefings / "z.md").write_bytes(b"x\n" * 501)
    r = _run(skills, tmp_path, forge_dir=forge)
    assert "CRIT: protocol" in r.stdout
    assert "x.md = 441 lines (cap 220)" in r.stdout
    assert "WARN: aspect" in r.stdout
    assert "y.md = 141 lines (cap 140)" in r.stdout
    assert "WARN: briefing" in r.stdout
    assert "z.md = 501 lines (cap 500)" in r.stdout
    assert r.returncode == 1  # CRIT from protocol


# 8. Default resolution (NO --forge-dir): protocols_dir/aspects_dir/forge_skill must resolve
# to the REAL forge-operations/ tree (not a dead team.forge path that 404s or silently
# no-ops). Proven by asserting on real protocol filenames that are known to exceed the cap
# today (hire.md=274, audit-skills.md=243 lines, cap 220) — this only appears in stdout if
# the protocols dir was actually globbed. This is the regression coverage for the
# symlink-retirement 404/skip (W4.3-fix): before the fix, protocols_dir/aspects_dir pointed
# at engine/skills/team.forge/... which no longer exists, so the glob silently found nothing
# and neither WARN line below would ever print. Shape-asserted (N > cap), NOT a frozen N:
# pinning exact counts re-broke on every hire.md edit (#62 dropped it 273→272, #63).
def test_default_forge_dirs_resolve_to_real_forge_operations(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    r = _run(skills, tmp_path, real_forge=True)  # no --forge-dir → default resolution
    assert r.returncode == 2, r.stdout + r.stderr  # WARN-only (no CRIT) as of this writing
    assert "WARN: protocol" in r.stdout
    for name in ("hire.md", "audit-skills.md"):
        m = re.search(rf"{re.escape(name)} = (\d+) lines \(cap 220\)", r.stdout)
        assert m, f"no WARN row for {name} — default resolution didn't glob real protocols/\n{r.stdout}"
        assert int(m.group(1)) > 220, f"{name} = {m.group(1)} lines, not over cap 220"
    assert "CRIT: forge-router" not in r.stdout
    assert "CRIT: protocol" not in r.stdout
    assert "CRIT: aspect" not in r.stdout
