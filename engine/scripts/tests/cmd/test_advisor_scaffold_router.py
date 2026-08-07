"""tests/cmd/test_advisor_scaffold_router.py — integration tests for `engine advisor scaffold-router`.

Hermetic: BARE tmp_path (NOT ai_root — avoid auto-seed and env pollution).
Mirrors tests/cmd/test_advisor_create.py's env/harness pattern (AC5, Task 5).
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.cmd.helpers import run_engine


def _scaffold_router(*args: str, tmp: Path, extra_env: dict | None = None) -> object:
    env = {"CONCLAVE_AI_ROOT": str(tmp), **(extra_env or {})}
    return run_engine("advisor", "scaffold-router", *args, env=env)


def test_cmd_scaffold_router(tmp_path):
    r = _scaffold_router("--id", "iris-cpo", tmp=tmp_path)
    assert r.returncode == 0, r.stderr

    skill_file = tmp_path / ".claude" / "skills" / "conclave-iris-cpo" / "SKILL.md"
    assert skill_file.is_file()
    assert "conclave-iris-cpo" in skill_file.read_text()

    info = json.loads(r.stdout)
    assert info["id"] == "iris-cpo"
    assert info["skill"] == str(skill_file)


def test_cmd_scaffold_router_invalid_id(tmp_path):
    r = _scaffold_router("--id", "Bad Id!", tmp=tmp_path)
    assert r.returncode == 1
    assert "invalid advisor id" in r.stderr


def test_cmd_scaffold_router_skips_enriched(tmp_path):
    """#58: re-run over an enriched wrapper skips (preserves it); --force overrides."""
    _scaffold_router("--id", "iris-cpo", tmp=tmp_path)
    skill_file = tmp_path / ".claude" / "skills" / "conclave-iris-cpo" / "SKILL.md"
    skill_file.write_text(skill_file.read_text() + "\n## Scope\n\ncustom\n")

    r = _scaffold_router("--id", "iris-cpo", tmp=tmp_path)  # re-run without --force
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout).get("skipped") == "enriched"
    assert "## Scope" in skill_file.read_text()  # preserved

    r = _scaffold_router("--id", "iris-cpo", "--force", tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "## Scope" not in skill_file.read_text()  # force re-render
