"""The corpus walk over `enginelib.records`' predicate.

The predicate itself is pinned in `test_records.py`. What is pinned here is the walk:
that it reaches records, names the file, and stays quiet on a clean corpus.
"""
from __future__ import annotations

from enginelib.audit import records as audit_records


def _rec(d, name, fm):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(f"---\n{fm}\n---\n\nbody\n", encoding="utf-8")


def test_a_lost_value_is_reported_and_names_its_file(tmp_path):
    """Reddens under: reporting without the filename — the operator's next move is to open
    the file, and a finding that does not say which one is a search, not a report.
    """
    _rec(tmp_path / "sessions", "2026-09-14-x.md", "issues: [#26]")
    found = audit_records.run([tmp_path / "sessions"])
    assert len(found.crit) == 1
    assert "2026-09-14-x.md" in found.crit[0]


def test_a_clean_corpus_reports_nothing(tmp_path):
    """Paired: a walk that reported everything would satisfy the test above."""
    _rec(tmp_path / "sessions", "ok.md", "advisor: sage-cto\nissues: [250,251]")
    assert audit_records.run([tmp_path / "sessions"]).crit == []


def test_the_walk_descends_into_subdirectories(tmp_path):
    """`mentions/<to>/open/` is two levels down. Reddens under: `glob` instead of `rglob`."""
    _rec(tmp_path / "mentions" / "kosmos-cxo" / "open", "m.md", "ref_issue: #297")
    assert len(audit_records.run([tmp_path / "mentions"]).crit) == 1


def test_a_missing_directory_is_not_an_error(tmp_path):
    """A fresh instance has no `mentions/`. Reddens under: letting the walk raise."""
    assert audit_records.run([tmp_path / "nope"]).crit == []
