"""tests/cmd/test_register_advisor.py — integration tests for `engine register advisor`.

Hermetic: bare tmp_path (NOT ai_root — its auto-seed adds 6 advisors and would
pollute assertions). Builds a controlled roster under:
  tmp/.claude/skills/conclave-<adv>/SKILL.md   (canonical; #48)
  tmp/.claude/agents/<adv>.md                  (bare id — the real mint layout)
and passes env={"CONCLAVE_AI_ROOT": str(tmp_path)}. discover_advisors returns
BARE ids, so tables/registry render `<id>` and look up agents/<id>.md.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from tests.cmd.helpers import run_engine


def _seed_advisor(tmp: Path, name: str, description: str | None = None,
                  layout: str = "conclave") -> None:
    """Write <prefix><name>/SKILL.md (conclave- canonical or legacy team.) and,
    when a description is given, the bare agents/<name>.md agent-def."""
    prefix = "conclave-" if layout == "conclave" else "team."
    skill_dir = tmp / ".claude" / "skills" / f"{prefix}{name}"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {prefix}{name}\n---\nstub\n")
    if description is not None:
        agent_file = tmp / ".claude" / "agents" / f"{name}.md"
        agent_file.parent.mkdir(parents=True, exist_ok=True)
        agent_file.write_text(f'description: "{description}"\n')


def _run(*args: str, tmp: Path) -> subprocess.CompletedProcess:
    return run_engine("register", "advisor", *args, env={"CONCLAVE_AI_ROOT": str(tmp)})


# 1. Dry-run preview — 2 advisors with descriptions
def test_dry_run_preview(tmp_path):
    _seed_advisor(tmp_path, "alpha", "First advisor")
    _seed_advisor(tmp_path, "beta", "Second advisor")
    r = _run("--dry-run", tmp=tmp_path)
    assert r.returncode == 0
    assert "=== CLAUDE.md Custom Agents (preview) ===" in r.stdout
    assert "| Agent | Purpose |" in r.stdout
    assert "| `alpha` | First advisor |" in r.stdout
    assert "| `beta` | Second advisor |" in r.stdout
    assert "=== Quorum Advisor Registry (preview) ===" in r.stdout
    assert "- alpha" in r.stdout
    assert "- beta" in r.stdout


# 1b. #48 dual-read: a legacy team.<id> skill dir is still discovered (bare id).
def test_legacy_team_layout_still_discovered(tmp_path):
    _seed_advisor(tmp_path, "gamma", "Legacy advisor", layout="team")
    r = _run("--dry-run", tmp=tmp_path)
    assert r.returncode == 0
    assert "| `gamma` | Legacy advisor |" in r.stdout
    assert "- gamma" in r.stdout


# 2. Lifecycle skills excluded — forge must not appear regardless of prefix
def test_lifecycle_excluded(tmp_path):
    _seed_advisor(tmp_path, "alpha", "Real advisor")
    forge_dir = tmp_path / ".claude" / "skills" / "conclave-forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / "SKILL.md").write_text("---\nname: conclave-forge\n---\n")
    r = _run("--dry-run", tmp=tmp_path)
    assert r.returncode == 0
    assert "forge" not in r.stdout
    assert "alpha" in r.stdout


# 3. Marker rebuild (non-dry) — markers to stdout, NOTE to stderr; exit 0
def test_marker_rebuild(tmp_path):
    _seed_advisor(tmp_path, "alpha", "First advisor")
    r = _run(tmp=tmp_path)
    assert r.returncode == 0
    assert "<!-- forge:registry:begin -->" in r.stdout
    assert "| Agent | Purpose |" in r.stdout
    assert "<!-- forge:registry:end -->" in r.stdout
    assert "NOTE: apply" in r.stderr


# 4. Missing/empty description → role "—"
def test_missing_description_dash(tmp_path):
    # no agent file at all
    skill_dir = tmp_path / ".claude" / "skills" / "conclave-noagent"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: conclave-noagent\n---\n")
    # agent file exists but has no description: line
    skill_dir2 = tmp_path / ".claude" / "skills" / "conclave-nodesc"
    skill_dir2.mkdir(parents=True, exist_ok=True)
    (skill_dir2 / "SKILL.md").write_text("---\nname: conclave-nodesc\n---\n")
    agent_file = tmp_path / ".claude" / "agents" / "nodesc.md"
    agent_file.parent.mkdir(parents=True, exist_ok=True)
    agent_file.write_text("some other content\n")
    r = _run("--dry-run", tmp=tmp_path)
    assert r.returncode == 0
    assert "| `noagent` | — |" in r.stdout
    assert "| `nodesc` | — |" in r.stdout


# 5. Sorted order — advisors seeded out of alpha order appear alphabetically
def test_sorted_order(tmp_path):
    _seed_advisor(tmp_path, "zebra", "Last")
    _seed_advisor(tmp_path, "apple", "First")
    _seed_advisor(tmp_path, "mango", "Middle")
    r = _run("--dry-run", tmp=tmp_path)
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    row_lines = [ln for ln in lines if ln.startswith("| `") and "Agent" not in ln]
    names = [ln.split("`")[1] for ln in row_lines]
    assert names == sorted(names)
    registry_lines = [ln for ln in lines if ln.startswith("- ")]
    reg_names = [ln[2:] for ln in registry_lines]
    assert reg_names == sorted(reg_names)
