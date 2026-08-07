"""Advisor ownership of a memory record is read from FRONTMATTER, not the filename.

Five call sites asked "which records are this advisor's?" with the glob
`*-<advisor>-*.md`, even though every record already carries the answer in a
frontmatter field. A glob answers an id change with an empty list rather than an
error: the reflexion buffer goes quiet, "Last sessions" empties, and nothing
reports a fault. That is silent memory loss, and it is what makes an id rename
dangerous in the first place.

The filename remains a FALLBACK for records written before the field existed, so
behaviour is 1:1 for legacy data — but a field, when present, always wins.
"""
from __future__ import annotations

from pathlib import Path

import session_init

from briefing import team_digest
from briefing.scans import code_repo, decisions, sessions
from enginelib.advisors import files_for_advisor
from tests.briefing.test_scans import make_ctx

ADVISOR = "vera-eng"


def _w(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sessions_dir(tmp: Path) -> Path:
    d = tmp / "agent-memory" / "advisors" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _renamed_session(tmp: Path, slug: str = "neon", reflexion: str = "a lesson") -> Path:
    """A record the advisor owns whose FILENAME still carries the retired id."""
    return _w(
        _sessions_dir(tmp) / f"2026-08-06-engineering-data-{slug}.md",
        f'---\nadvisor: {ADVISOR}\ndate: 2026-08-06\nslug: {slug}\n'
        f'reflexion: "{reflexion}"\n---\n\nBody.\n',
    )


# ---------------------------------------------------------------------------
# The shared helper
# ---------------------------------------------------------------------------

def test_claims_a_record_whose_field_names_the_advisor_despite_the_filename(tmp_path):
    f = _renamed_session(tmp_path)
    assert files_for_advisor(_sessions_dir(tmp_path), ADVISOR, field="advisor") == [f]


def test_rejects_a_record_whose_filename_matches_but_whose_field_names_another(tmp_path):
    _w(
        _sessions_dir(tmp_path) / f"2026-08-06-{ADVISOR}-borrowed.md",
        "---\nadvisor: someone-else\n---\n",
    )
    assert files_for_advisor(_sessions_dir(tmp_path), ADVISOR, field="advisor") == []


def test_falls_back_to_the_filename_when_the_field_is_absent(tmp_path):
    f = _w(_sessions_dir(tmp_path) / f"2026-08-06-{ADVISOR}-legacy.md", "no frontmatter here\n")
    assert files_for_advisor(_sessions_dir(tmp_path), ADVISOR, field="advisor") == [f]


def test_reads_the_named_field_so_decisions_can_use_by(tmp_path):
    d = tmp_path / "decisions"
    f = _w(d / "2026-08-06-engineering-data-no-merge.md", f"---\nby: {ADVISOR}\n---\n")
    assert files_for_advisor(d, ADVISOR, field="by") == [f]
    assert files_for_advisor(d, ADVISOR, field="advisor") == []


def test_missing_directory_yields_nothing(tmp_path):
    assert files_for_advisor(tmp_path / "absent", ADVISOR, field="advisor") == []


# ---------------------------------------------------------------------------
# The five consumers
# ---------------------------------------------------------------------------

def test_reflexion_buffer_survives_a_rename(tmp_path):
    _renamed_session(tmp_path, reflexion="measure before calling it impossible")
    (tmp_path / "ops").mkdir(exist_ok=True)
    items = session_init._step1c_reflexion(ADVISOR, tmp_path)
    assert any("measure before calling it impossible" in i for i in items), items


def test_last_sessions_section_survives_a_rename(tmp_path):
    f = _renamed_session(tmp_path)
    out = sessions.build(make_ctx(tmp_path, ADVISOR))
    assert f.stem in out, out


def test_recent_decisions_section_survives_a_rename(tmp_path):
    f = _w(
        tmp_path / "agent-memory" / "advisors" / "decisions"
        / "2026-08-06-engineering-data-no-merge.md",
        f"---\nslug: no-merge\nby: {ADVISOR}\n---\n",
    )
    out = decisions.build(make_ctx(tmp_path, ADVISOR))
    assert f.stem in out, out


def test_code_repo_cutoff_survives_a_rename(tmp_path):
    _renamed_session(tmp_path)
    assert code_repo._last_session_mtime(make_ctx(tmp_path, ADVISOR)) is not None


def test_team_digest_last_session_survives_a_rename(tmp_path, monkeypatch):
    _renamed_session(tmp_path, slug="promo-stack")
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    assert team_digest._last_session(ADVISOR) != "—"
