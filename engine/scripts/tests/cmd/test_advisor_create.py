"""tests/cmd/test_advisor_create.py — integration tests for `engine advisor create`.

Hermetic: BARE tmp_path (NOT ai_root — avoid auto-seed and env pollution).
Agent file lands at tmp/.claude/agents/<id>.md when CONCLAVE_AI_ROOT=str(tmp).
Template is read from the real (updated) engine template via templates_dir().
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.cmd.helpers import run_engine


def _create(*args: str, tmp: Path, extra_env: dict | None = None) -> object:
    env = {"CONCLAVE_AI_ROOT": str(tmp), **(extra_env or {})}
    return run_engine("advisor", "create", *args, env=env)


# 1. Happy path + FLAT gate
def test_happy_path_flat(tmp_path):
    r = _create("--id", "testx", "--role", "QA", "--color", "blue", tmp=tmp_path)
    assert r.returncode == 0, r.stderr

    agent_file = tmp_path / ".claude" / "agents" / "testx.md"
    assert agent_file.exists(), "agent file not created"

    content = agent_file.read_text()
    assert "name: testx" in content, "name must be bare id (flat layout)"
    assert "team." not in content, "no team.<id> references in flat agent-def"

    import json
    info = json.loads(r.stdout)
    assert info["id"] == "testx"
    assert info["agent"].endswith("testx.md")


# 2. Defaults: no --name/--emoji/--tone → 🧭 and pragmatic appear
def test_defaults(tmp_path):
    r = _create("--id", "testx", "--role", "QA", "--color", "blue", tmp=tmp_path)
    assert r.returncode == 0, r.stderr

    content = (tmp_path / ".claude" / "agents" / "testx.md").read_text()
    assert "🧭" in content, "default emoji 🧭 must appear in file"
    assert "pragmatic" in content, "default tone must appear in file"


# 3. Collision: creating the same id twice → exit 2, stderr "already exists"
def test_collision(tmp_path):
    r1 = _create("--id", "testx", "--role", "QA", "--color", "blue", tmp=tmp_path)
    assert r1.returncode == 0, r1.stderr

    r2 = _create("--id", "testx", "--role", "QA", "--color", "blue", tmp=tmp_path)
    assert r2.returncode == 2
    assert "already exists" in r2.stderr


# 4. Invalid id: uppercase, slash, space → exit 1, stderr "invalid --id"
@pytest.mark.parametrize("bad_id", ["TestX", "has/slash", "has space"])
def test_invalid_id(tmp_path, bad_id):
    r = _create("--id", bad_id, "--role", "QA", "--color", "blue", tmp=tmp_path)
    assert r.returncode == 1
    assert "invalid --id" in r.stderr


# 5. Missing required --role → exit 1, stderr contains "usage"
def test_missing_role(tmp_path):
    r = _create("--id", "testx", "--color", "blue", tmp=tmp_path)
    assert r.returncode == 1
    assert "usage" in r.stderr


# 6. project_name from roster — seed roster.yaml; check "for Acme." appears
def test_project_name_from_roster(tmp_path):
    (tmp_path / "roster.yaml").write_text("project:\n  name: Acme\n")
    r = _create("--id", "testx", "--role", "QA", "--color", "blue", tmp=tmp_path)
    assert r.returncode == 0, r.stderr

    content = (tmp_path / ".claude" / "agents" / "testx.md").read_text()
    assert "for Acme." in content, f"roster project.name not rendered:\n{content}"


# 6b. No roster → "the project" default
def test_project_name_default(tmp_path):
    r = _create("--id", "testx", "--role", "QA", "--color", "blue", tmp=tmp_path)
    assert r.returncode == 0, r.stderr

    content = (tmp_path / ".claude" / "agents" / "testx.md").read_text()
    assert "for the project." in content, f"default project name not rendered:\n{content}"


# 7. #55: mint provisions memory/personality.md so the briefing personality_path
#    resolves to a real file (not the 'not yet written' placeholder).
def test_mint_provisions_personality(tmp_path):
    r = _create("--id", "testx", "--role", "QA", "--color", "blue", tmp=tmp_path)
    assert r.returncode == 0, r.stderr

    pmd = tmp_path / ".claude" / "skills" / "conclave-testx" / "memory" / "personality.md"
    assert pmd.is_file(), "personality.md stub not provisioned on mint"
    body = pmd.read_text()
    assert "testx" in body, "advisor id not substituted into personality stub"
    assert "{{advisor}}" not in body, "mustache placeholder left unsubstituted"


# 8. #55: minted wrapper carries a forge: block with model-version, so
#    `engine model bump` has a target instead of silently skip-no-forge.
def test_mint_writes_forge_block(tmp_path):
    r = _create("--id", "testx", "--role", "QA", "--color", "blue", tmp=tmp_path)
    assert r.returncode == 0, r.stderr

    wrapper = (tmp_path / ".claude" / "skills" / "conclave-testx" / "SKILL.md").read_text()
    assert "\nforge:" in wrapper, "no forge: block minted into wrapper frontmatter"
    assert "model-version:" in wrapper
    assert "hired-by: forge" in wrapper
    # forge: must sit INSIDE the frontmatter (before the closing '---').
    head = wrapper.split("---", 2)
    assert len(head) >= 3 and "forge:" in head[1], "forge: block not in frontmatter"
