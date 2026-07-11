"""tests/cmd/test_skill_stocktake.py — characterization tests for `engine skill stocktake`.

Ports skill-stocktake.sh behavior into pytest. There was no prior bats test for this
script — these are the first characterization tests.

Verdict cascade (order matters — first hit wins):
  1. has_name == 0 OR has_description == 0  → Improve(frontmatter)
  2. lines < 30                              → Improve(stub)
  3. age_days > 180 AND invocations < 2     → Retire(stale+unused)
  4. invocations == 0 AND age_days > 90     → Retire(unused)
  5. else                                   → Keep

Core function (stocktake_rows) is tested directly with a fixed now_epoch for
determinism; mtime is set via os.utime. Adapter (run_engine) is used for smoke
tests of the two output modes and the no-skills-dir error path.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

from enginelib.skill import stocktake_rows
from tests.cmd.helpers import run_engine

# Fixed epoch used for all core (non-subprocess) tests.
_NOW = 1_000_000_000


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_skill(skills_dir: Path, name: str, content: str) -> Path:
    """Create a skill dir + SKILL.md with the given content; return the SKILL.md path."""
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    md = d / "SKILL.md"
    md.write_text(content, encoding="utf-8")
    return md


def _set_age(path: Path, age_days: int, now_epoch: int) -> None:
    """Stamp path's mtime so (now_epoch - mtime) // 86400 == age_days."""
    mtime = now_epoch - age_days * 86400
    os.utime(path, (mtime, mtime))


def _fm_content(name: str, nlines_target: int) -> str:
    """Return SKILL.md content with both `name:` and `description:` and ~nlines_target newlines.

    Header contributes 2 newlines; body fills the remainder.
    """
    header = f"name: {name}\ndescription: A test skill named {name}.\n"
    body_count = max(0, nlines_target - 2)
    body = "\n".join(f"body line {i}" for i in range(body_count))
    return header + body + ("\n" if body_count > 0 else "")


# ── verdict cascade (core, fixed now_epoch) ────────────────────────────────────


def test_verdict_keep(tmp_path):
    """≥30 lines, valid frontmatter, age ≤ 7, ≥ 2 invocations → Keep."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    md = _make_skill(skills_dir, "keep-skill", _fm_content("keep-skill", 31))
    _set_age(md, 5, _NOW)

    # Two session lines matching "Skill: keep-skill" → invocations == 2
    (sessions_dir / "session1.md").write_text(
        "Skill: keep-skill\nsome noise\nSkill: keep-skill\n", encoding="utf-8"
    )

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    assert len(rows) == 1
    row = rows[0]
    assert row["verdict"] == "Keep"
    assert row["age_days"] == 5
    assert row["invocations"] == 2
    assert row["lines"] >= 30


def test_verdict_improve_frontmatter_missing_description(tmp_path):
    """has_name present but no `description:` → Improve(frontmatter) (rule 1)."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"

    content = "name: fm-skill\n" + "\n".join(f"line {i}" for i in range(35)) + "\n"
    md = _make_skill(skills_dir, "fm-skill", content)
    _set_age(md, 5, _NOW)

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    assert rows[0]["verdict"] == "Improve(frontmatter)"


def test_verdict_improve_frontmatter_missing_name(tmp_path):
    """No `name:` field at all → Improve(frontmatter) (rule 1)."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"

    content = "description: A skill.\n" + "\n".join(f"line {i}" for i in range(35)) + "\n"
    md = _make_skill(skills_dir, "noname-skill", content)
    _set_age(md, 5, _NOW)

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    assert rows[0]["verdict"] == "Improve(frontmatter)"


def test_verdict_improve_stub(tmp_path):
    """Valid frontmatter but < 30 lines → Improve(stub) (rule 2)."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"

    # 10 total newlines (2 header + 8 body) → nlines=10 < 30
    content = _fm_content("stub-skill", 10)
    md = _make_skill(skills_dir, "stub-skill", content)
    _set_age(md, 5, _NOW)

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    row = rows[0]
    assert row["verdict"] == "Improve(stub)"
    assert row["lines"] < 30


def test_verdict_retire_stale_unused(tmp_path):
    """age > 180, invocations < 2, valid frontmatter, ≥ 30 lines → Retire(stale+unused) (rule 3)."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"

    md = _make_skill(skills_dir, "stale-skill", _fm_content("stale-skill", 31))
    _set_age(md, 200, _NOW)  # 200 > 180; no sessions dir seeded → invocations=0 < 2

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    row = rows[0]
    assert row["verdict"] == "Retire(stale+unused)"
    assert row["age_days"] == 200
    assert row["invocations"] == 0


def test_verdict_retire_unused(tmp_path):
    """invocations == 0, age > 90 but ≤ 180 → Retire(unused) (rule 4); rule 3 must not pre-empt."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"

    # age=100: satisfies rule 4 (>90) but NOT rule 3 (100 ≤ 180)
    md = _make_skill(skills_dir, "unused-skill", _fm_content("unused-skill", 31))
    _set_age(md, 100, _NOW)

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    row = rows[0]
    assert row["verdict"] == "Retire(unused)"
    assert row["age_days"] == 100
    assert row["invocations"] == 0


def test_verdict_missing_skillmd(tmp_path):
    """Skill dir with no SKILL.md → verdict 'missing_skillmd'; age/invocations/mtime = 'N/A'."""
    skills_dir = tmp_path / ".claude" / "skills"
    (skills_dir / "no-md-skill").mkdir(parents=True, exist_ok=True)  # dir only, no SKILL.md

    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "no-md-skill"
    assert row["verdict"] == "missing_skillmd"
    assert row["age_days"] == "N/A"
    assert row["invocations"] == "N/A"
    assert row["mtime"] == "N/A"
    assert row["lines"] == 0
    assert row["bytes"] == 0


def test_invocation_via_skill_colon_pattern(tmp_path):
    """'Skill: <name>' in session file counts as one invocation."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    md = _make_skill(skills_dir, "my-skill", _fm_content("my-skill", 31))
    _set_age(md, 50, _NOW)  # age=50 → keep unless invocations==0 (rule 4 needs age>90)

    (sessions_dir / "sess.md").write_text(
        "Skill: my-skill\nother line\n", encoding="utf-8"
    )

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    assert rows[0]["invocations"] == 1


def test_invocation_via_slash_pattern(tmp_path):
    """`/<name> ` in session file counts as one invocation."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    md = _make_skill(skills_dir, "slash-skill", _fm_content("slash-skill", 31))
    _set_age(md, 50, _NOW)

    (sessions_dir / "sess.md").write_text(
        "invoked /slash-skill today\n", encoding="utf-8"
    )

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    assert rows[0]["invocations"] == 1


def test_cascade_rule1_beats_rule2(tmp_path):
    """Frontmatter missing description + < 30 lines → rule 1 wins (Improve(frontmatter))."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"

    content = "name: mixed-skill\n" + "x\n" * 5  # no description:, only 6 lines
    md = _make_skill(skills_dir, "mixed-skill", content)
    _set_age(md, 5, _NOW)

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    assert rows[0]["verdict"] == "Improve(frontmatter)"  # not Improve(stub)


def test_cascade_rule3_beats_rule4(tmp_path):
    """age > 180, invocations == 0 → rule 3 wins (Retire(stale+unused)), not rule 4."""
    skills_dir = tmp_path / ".claude" / "skills"
    sessions_dir = tmp_path / "agent-memory" / "advisors" / "sessions"

    md = _make_skill(skills_dir, "super-stale", _fm_content("super-stale", 31))
    _set_age(md, 200, _NOW)  # age=200 > 180; invocations=0 < 2

    rows = stocktake_rows(skills_dir, sessions_dir, _NOW)
    assert rows[0]["verdict"] == "Retire(stale+unused)"  # not Retire(unused)


# ── --quick mode smoke (run_engine) ────────────────────────────────────────────


def test_quick_mode_shows_header_and_recent_skill(tmp_path, monkeypatch):
    """--quick: lists recently-changed skills and excludes old ones."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))

    skills_dir = tmp_path / ".claude" / "skills"
    now_epoch = int(time.time())

    # Recent skill (age 2 days) — should appear
    md_r = _make_skill(skills_dir, "recent-skill", _fm_content("recent-skill", 31))
    _set_age(md_r, 2, now_epoch)

    # Old skill (age 30 days) — should NOT appear in --quick
    md_o = _make_skill(skills_dir, "old-skill", _fm_content("old-skill", 31))
    _set_age(md_o, 30, now_epoch)

    r = run_engine("skill", "stocktake", "--quick")
    assert r.returncode == 0, r.stderr
    assert "Skill Stocktake — quick mode" in r.stdout
    assert "recent-skill" in r.stdout
    assert "old-skill" not in r.stdout
    assert "Total skills changed in last 7d:" in r.stdout


def test_quick_mode_is_default(tmp_path, monkeypatch):
    """No mode flag → defaults to --quick output."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    (tmp_path / ".claude" / "skills" / "any-skill").mkdir(parents=True, exist_ok=True)
    md = (tmp_path / ".claude" / "skills" / "any-skill" / "SKILL.md")
    md.write_text(_fm_content("any-skill", 31), encoding="utf-8")

    r = run_engine("skill", "stocktake")
    assert r.returncode == 0, r.stderr
    assert "Skill Stocktake — quick mode" in r.stdout


# ── --full mode smoke (run_engine) ─────────────────────────────────────────────


def test_full_mode_writes_json_and_prints_summary(tmp_path, monkeypatch):
    """--full: writes JSON file, stdout has 'Wrote' and 'Verdict summary:'."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))

    skills_dir = tmp_path / ".claude" / "skills"
    now_epoch = int(time.time())

    md = _make_skill(skills_dir, "full-skill", _fm_content("full-skill", 31))
    _set_age(md, 10, now_epoch)

    r = run_engine("skill", "stocktake", "--full")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0].startswith("Skill Stocktake — full mode → ")
    assert "Wrote " in r.stdout
    assert "Verdict summary:" in r.stdout

    today = date.today().isoformat()
    out_file = tmp_path / "agent-memory" / "skill-stocktake" / f"{today}-results.json"
    assert out_file.is_file(), f"expected JSON at {out_file}"

    data = json.loads(out_file.read_text())
    assert data["mode"] == "full"
    assert data["date"] == today
    assert isinstance(data["skills"], list)
    assert len(data["skills"]) == 1
    assert data["skills"][0]["name"] == "full-skill"


# ── error path ─────────────────────────────────────────────────────────────────


def test_no_skills_dir_exits_1(tmp_path, monkeypatch):
    """No .claude/skills dir → exit 1 with 'no skills dir' in stderr."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    # Deliberately do NOT create .claude/skills
    r = run_engine("skill", "stocktake")
    assert r.returncode == 1
    assert "no skills dir" in r.stderr
