"""test_registry_advisors.py — briefing._registry_advisors prefix tolerance (#48).

_registry_advisors derives the on-disk advisor set for briefing's unknown-advisor
guard. It must recognize the canonical conclave-<id> layout, not only legacy team.<id>.
"""
from __future__ import annotations

from briefing.__main__ import _registry_advisors


def _seed_skill(root, dirname: str) -> None:
    d = root / ".claude" / "skills" / dirname
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\nname: x\n---\nstub\n")


def test_discovers_conclave_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    _seed_skill(tmp_path, "conclave-iris")
    assert "iris" in _registry_advisors()


def test_discovers_legacy_team_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    _seed_skill(tmp_path, "team.nexus-ceo")
    assert "nexus-ceo" in _registry_advisors()


def test_excludes_lifecycle_regardless_of_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    _seed_skill(tmp_path, "conclave-forge")
    _seed_skill(tmp_path, "team.hire")
    _seed_skill(tmp_path, "conclave-sage-cto")
    advisors = _registry_advisors()
    assert "sage-cto" in advisors
    assert "forge" not in advisors
    assert "hire" not in advisors
