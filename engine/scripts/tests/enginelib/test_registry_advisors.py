"""enginelib.advisors.registry_advisors — the SKILL-dir half of advisor discovery (#48).

These cases were written against `briefing.__main__._registry_advisors`, which existed
to feed the briefing admission gate. #133 F1 routed that gate onto the agent-defs, so
the private copy is gone — but its public successor, the one `register.discover_advisors`
calls, had no direct coverage of its own. Re-pointed rather than deleted: what they
assert is the migration rule (both skill-dir prefixes are recognised) and the lifecycle
exclusion, and both still bind wherever the SKILL-dir registry is the question asked.

The question is no longer "who may hold a briefing" — that is `known_advisors` — but
"what routers exist on disk", which `engine audit registry-consistency` compares against
the agent-defs to report a router minted without one.
"""
from __future__ import annotations

from enginelib.advisors import registry_advisors


def _seed_skill(base, dirname: str) -> None:
    d = base / dirname
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\nname: x\n---\nstub\n", encoding="utf-8")


def test_discovers_conclave_layout(tmp_path):
    _seed_skill(tmp_path, "conclave-iris-cpo")
    assert "iris-cpo" in registry_advisors(tmp_path)


def test_discovers_legacy_team_layout(tmp_path):
    _seed_skill(tmp_path, "team.nexus-ceo")
    assert "nexus-ceo" in registry_advisors(tmp_path)


def test_excludes_lifecycle_regardless_of_prefix(tmp_path):
    _seed_skill(tmp_path, "conclave-forge")
    _seed_skill(tmp_path, "team.hire")
    _seed_skill(tmp_path, "conclave-sage-cto")
    advisors = registry_advisors(tmp_path)
    assert "sage-cto" in advisors
    assert "forge" not in advisors
    assert "hire" not in advisors
