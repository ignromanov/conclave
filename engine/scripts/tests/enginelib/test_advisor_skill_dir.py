"""test_advisor_skill_dir.py — the #48 prefix-tolerant SKILL-dir resolver.

Hermetic: operates on tmp dirs only, no ambient DATA/CODE tree.
"""
from __future__ import annotations

from enginelib.paths import advisor_skill_dir, iter_advisor_skills


def test_prefers_conclave_layout(tmp_path):
    """When both layouts exist, the current conclave-<id> wins over legacy team.<id>."""
    (tmp_path / "conclave-sage-cto").mkdir()
    (tmp_path / "team.sage-cto").mkdir()
    assert advisor_skill_dir("sage-cto", tmp_path) == tmp_path / "conclave-sage-cto"


def test_falls_back_to_legacy_team_layout(tmp_path):
    """Only the legacy team.<id> dir exists → dual-read resolves it (migration)."""
    (tmp_path / "team.nexus-ceo").mkdir()
    assert advisor_skill_dir("nexus-ceo", tmp_path) == tmp_path / "team.nexus-ceo"


def test_neither_exists_returns_canonical_conclave_path(tmp_path):
    """Nothing on disk → return the canonical conclave-<id> path (for writes/reads
    that provision fresh), never the legacy prefix."""
    assert advisor_skill_dir("newbie", tmp_path) == tmp_path / "conclave-newbie"


def test_conclave_wins_even_when_only_it_exists(tmp_path):
    (tmp_path / "conclave-iris").mkdir()
    assert advisor_skill_dir("iris", tmp_path) == tmp_path / "conclave-iris"


# --- iter_advisor_skills: the #54 shared dual-prefix discovery helper ----------

def _mkskill(base, dirname):
    d = base / dirname
    d.mkdir()
    (d / "SKILL.md").write_text("stub", encoding="utf-8")
    return d / "SKILL.md"


def test_iter_discovers_both_prefixes(tmp_path):
    """A conclave-<id> advisor AND a legacy team.<id> one are both discovered,
    yielded as (bare_id, skill_md), globally sorted by bare id."""
    _mkskill(tmp_path, "conclave-sage-cto")
    _mkskill(tmp_path, "team.nexus-ceo")
    result = list(iter_advisor_skills(tmp_path))
    assert [bare for bare, _ in result] == ["nexus-ceo", "sage-cto"]
    assert result[1][1] == tmp_path / "conclave-sage-cto" / "SKILL.md"


def test_iter_dedupes_preferring_conclave(tmp_path):
    """When both layouts exist for the same id, the id appears once, resolved to
    the canonical conclave-<id> SKILL.md."""
    _mkskill(tmp_path, "conclave-kai-cto")
    _mkskill(tmp_path, "team.kai-cto")
    result = dict(iter_advisor_skills(tmp_path))
    assert list(result) == ["kai-cto"]
    assert result["kai-cto"] == tmp_path / "conclave-kai-cto" / "SKILL.md"


def test_iter_yields_lifecycle_dirs_too(tmp_path):
    """The helper does not filter lifecycle — callers apply their own bare-id
    exclusion sets (their exclusion semantics differ)."""
    _mkskill(tmp_path, "conclave-start")
    _mkskill(tmp_path, "conclave-dev")
    assert set(dict(iter_advisor_skills(tmp_path))) == {"start", "dev"}


def test_iter_empty_base_yields_nothing(tmp_path):
    assert list(iter_advisor_skills(tmp_path)) == []
