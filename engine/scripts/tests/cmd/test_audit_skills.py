"""tests/cmd/test_audit_skills.py — integration tests for `engine audit skills`.

Hermeticity strategy: BARE tmp_path (NOT ai_root fixture — it auto-seeds 6 advisors).
Two env seams:
  CONCLAVE_AI_ROOT      → project skills at <tmp_ai>/.claude/skills
                          report output at <tmp_ai>/agent-memory/advisors/audits
  CONCLAVE_CLAUDE_HOME  → user skills at <tmp_home>/skills
                          plugins at <tmp_home>/plugins/installed_plugins.json
                          settings at <tmp_home>/settings.json
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from tests.cmd.helpers import run_engine


def _setup(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    """Return (user_skills, project_skills, audit_dir, env)."""
    tmp_ai = tmp_path / "ai"
    tmp_home = tmp_path / "home"
    user_skills = tmp_home / "skills"
    project_skills = tmp_ai / ".claude" / "skills"
    audit_dir = tmp_ai / "agent-memory" / "advisors" / "audits"
    user_skills.mkdir(parents=True)
    project_skills.mkdir(parents=True)
    env = {
        "CONCLAVE_AI_ROOT": str(tmp_ai),
        "CONCLAVE_CLAUDE_HOME": str(tmp_home),
    }
    return user_skills, project_skills, audit_dir, env


def _write_plugins(tmp_home: Path, plugins: dict) -> None:
    p = tmp_home / "plugins" / "installed_plugins.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"plugins": plugins}), encoding="utf-8")


def _write_settings(tmp_home: Path, enabled_plugins: dict) -> None:
    p = tmp_home / "settings.json"
    p.write_text(json.dumps({"enabledPlugins": enabled_plugins}), encoding="utf-8")


def test_writes_report_and_stdout(tmp_path):
    """Writes report file + stdout lines; front-matter + title present."""
    user_skills, project_skills, audit_dir, env = _setup(tmp_path)
    tmp_home = tmp_path / "home"
    today = datetime.date.today().isoformat()

    (user_skills / "skill-alpha").mkdir()
    (user_skills / "skill-beta").mkdir()
    (project_skills / "proj-skill").mkdir()
    _write_plugins(tmp_home, {"plug-a": [], "plug-b": []})
    _write_settings(tmp_home, {"plug-a": True, "plug-b": True})

    r = run_engine("audit", "skills", env=env)

    assert r.returncode == 0
    assert "[audit-skills] wrote=" in r.stdout
    assert "user-skills=2 project-skills=1 plugins=2" in r.stdout

    report = audit_dir / f"{today}-skills.md"
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    assert "protocol: audit-skills" in content
    assert "version: 1.0.0" in content
    assert f"# Skills/Plugins Inventory — {today}" in content


def test_quiet_suppresses_stdout(tmp_path):
    """--quiet: exit 0, stdout empty, file still written."""
    user_skills, project_skills, audit_dir, env = _setup(tmp_path)
    tmp_home = tmp_path / "home"
    today = datetime.date.today().isoformat()

    (user_skills / "skill-alpha").mkdir()
    (user_skills / "skill-beta").mkdir()
    (project_skills / "proj-skill").mkdir()
    _write_plugins(tmp_home, {"plug-a": [], "plug-b": []})
    _write_settings(tmp_home, {"plug-a": True, "plug-b": True})

    r = run_engine("audit", "skills", "--quiet", env=env)

    assert r.returncode == 0
    assert r.stdout.strip() == ""

    report = audit_dir / f"{today}-skills.md"
    assert report.exists()


def test_s3_groups_cluster(tmp_path):
    """S3 GROUPS: bash-pro + bash-scripting → **bash** (2×): cluster."""
    user_skills, project_skills, audit_dir, env = _setup(tmp_path)

    (user_skills / "bash-pro").mkdir()
    (user_skills / "bash-scripting").mkdir()

    r = run_engine("audit", "skills", "--quiet", env=env)

    assert r.returncode == 0
    content = (audit_dir / f"{datetime.date.today().isoformat()}-skills.md").read_text(
        encoding="utf-8"
    )
    assert "**bash** (2×):" in content
    assert "bash-pro" in content
    assert "bash-scripting" in content


def test_s8_sleeping_and_disabled(tmp_path):
    """S8 sleeping plugin + currently-disabled section both populated."""
    user_skills, project_skills, audit_dir, env = _setup(tmp_path)
    tmp_home = tmp_path / "home"

    _write_plugins(tmp_home, {"foo": []})
    _write_settings(tmp_home, {"bar": False})

    r = run_engine("audit", "skills", "--quiet", env=env)

    assert r.returncode == 0
    content = (audit_dir / f"{datetime.date.today().isoformat()}-skills.md").read_text(
        encoding="utf-8"
    )
    # S8: foo installed but absent from enabledPlugins map
    s8_idx = content.index("### S8")
    s8_section = content[s8_idx : content.index("\n\n###", s8_idx)]
    assert "Count: 1" in s8_section
    assert "- foo" in s8_section

    # Currently disabled: bar is false
    assert "- bar" in content


def test_quarantine_excluded_and_missing_json_graceful(tmp_path):
    """_quarantine dir excluded from count; missing JSON → graceful (no crash, plugins=0)."""
    user_skills, project_skills, audit_dir, env = _setup(tmp_path)

    (user_skills / "real-skill").mkdir()
    (user_skills / "_quarantine").mkdir()
    # no plugins/settings JSON files

    r = run_engine("audit", "skills", env=env)

    assert r.returncode == 0
    assert "user-skills=1" in r.stdout
    assert "plugins=0" in r.stdout

    content = (audit_dir / f"{datetime.date.today().isoformat()}-skills.md").read_text(
        encoding="utf-8"
    )
    assert "| Loose user skills" in content
    # _quarantine must not appear in the skill listing
    assert "_quarantine" not in content


def test_s10_project_scoped_duplicate(tmp_path):
    """S10: plugin with both project + user scope instances → listed under S10."""
    user_skills, project_skills, audit_dir, env = _setup(tmp_path)
    tmp_home = tmp_path / "home"

    _write_plugins(
        tmp_home,
        {
            "my-plugin": [
                {"scope": "user"},
                {"scope": "project", "projectPath": "/some/project"},
            ]
        },
    )
    _write_settings(tmp_home, {})

    r = run_engine("audit", "skills", "--quiet", env=env)

    assert r.returncode == 0
    content = (audit_dir / f"{datetime.date.today().isoformat()}-skills.md").read_text(
        encoding="utf-8"
    )
    s10_idx = content.index("### S10")
    s10_section = content[s10_idx : content.index("\n\n###", s10_idx)]
    assert "my-plugin" in s10_section
    assert "project:" in s10_section
