"""test_personality_path.py — where an advisor's personality.md is read from.

A hired advisor's persona is instance data and lives beside its minted router. A
META advisor's ships with the engine and no instance ever writes it, so anchoring
both on the project skills dir left Forge's 'Who I am' blank in every instance.

Hermetic: tmp dirs plus CONCLAVE_ENGINE_ROOT, no ambient DATA/CODE tree.
"""
from __future__ import annotations

from enginelib.advisors import META_ADVISORS, personality_path

_META = sorted(META_ADVISORS)[0]


def _shipped(tmp_path, monkeypatch, body: str | None = "Forge voice"):
    """Point forge_dir() at a tmp tree; optionally write the shipped persona.

    forge_dir() is engine_root().parent/skills/forge-operations, so setting
    CONCLAVE_ENGINE_ROOT to <tmp>/engine puts it at <tmp>/skills/forge-operations.
    """
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(tmp_path / "engine"))
    path = tmp_path / "skills" / "forge-operations" / "memory" / "personality.md"
    if body is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return path


def _project_persona(skills_base, advisor_id: str, body: str = "instance voice"):
    path = skills_base / f"conclave-{advisor_id}" / "memory" / "personality.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_meta_advisor_falls_back_to_the_shipped_persona(tmp_path, monkeypatch):
    """Forge's persona is CODE, versioned with the skill it describes. Nothing
    writes it into an instance, so the project anchor is empty by construction and
    resolving there yields the 'not yet written' placeholder for every consumer."""
    shipped = _shipped(tmp_path, monkeypatch)
    skills = tmp_path / ".claude" / "skills"
    skills.mkdir(parents=True)
    assert personality_path(_META, skills) == shipped


def test_meta_advisor_prefers_an_instance_written_persona(tmp_path, monkeypatch):
    """The fallback must not override an instance that enriched its own Forge —
    a shipped default loses to local data, never the other way round."""
    _shipped(tmp_path, monkeypatch)
    skills = tmp_path / ".claude" / "skills"
    own = _project_persona(skills, _META)
    assert personality_path(_META, skills) == own


def test_hired_advisor_never_inherits_the_shipped_persona(tmp_path, monkeypatch):
    """The negative that matters: a domain advisor with no persona of its own must
    resolve to its OWN empty path, so the briefing says 'not yet written'. Falling
    back for everyone would hand every advisor in every instance Forge's voice."""
    _shipped(tmp_path, monkeypatch)
    skills = tmp_path / ".claude" / "skills"
    skills.mkdir(parents=True)
    resolved = personality_path("nexus-ceo", skills)
    assert resolved == skills / "conclave-nexus-ceo" / "memory" / "personality.md"
    assert not resolved.is_file()


def test_hired_advisor_resolves_its_own_persona(tmp_path, monkeypatch):
    _shipped(tmp_path, monkeypatch)
    skills = tmp_path / ".claude" / "skills"
    own = _project_persona(skills, "nexus-ceo")
    assert personality_path("nexus-ceo", skills) == own


def test_meta_advisor_with_no_shipped_copy_returns_its_project_path(tmp_path, monkeypatch):
    """A checkout without the forge-operations skill (a trimmed install) must still
    yield a usable path rather than one pointing into a directory that is not there
    — the caller renders a placeholder, which is the honest answer."""
    _shipped(tmp_path, monkeypatch, body=None)
    skills = tmp_path / ".claude" / "skills"
    skills.mkdir(parents=True)
    assert personality_path(_META, skills) == (
        skills / f"conclave-{_META}" / "memory" / "personality.md"
    )


def test_legacy_team_prefix_still_resolves(tmp_path, monkeypatch):
    """The #48 dual-prefix read is not lost: sage-cto's persona sits under team.
    on the dev instance and must keep resolving."""
    _shipped(tmp_path, monkeypatch)
    skills = tmp_path / ".claude" / "skills"
    legacy = skills / "team.sage-cto" / "memory" / "personality.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("Sage voice", encoding="utf-8")
    assert personality_path("sage-cto", skills) == legacy
