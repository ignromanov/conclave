"""`engine memory index` reports records whose written value did not survive (#249 item 1).

The index rebuild is the surface that catches what the close cannot: a hand edit to a
record written days earlier. It reports and does not refuse — an instance already holding
damaged records must not have its rebuild locked until someone runs a migration.
"""
from __future__ import annotations

from enginelib.paths import sessions_dir
from tests.cmd.helpers import run_engine


def _session(name: str, fm: str) -> None:
    d = sessions_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(f"---\n{fm}\n---\n\nbody\n", encoding="utf-8")


def test_a_hand_edited_record_is_reported_by_the_rebuild(seed_advisors):
    """The live case, verbatim. Reddens under: removing `_report_lost_values`."""
    seed_advisors("nexus-ceo")
    _session("2026-09-14-nexus-ceo-x.md", "advisor: nexus-ceo\nissues: [#26]")
    r = run_engine("memory", "index", "--now", "2026-09-15")
    assert "2026-09-14-nexus-ceo-x.md" in r.stderr
    assert "1 record(s) lost a value" in r.stderr


def test_the_rebuild_still_succeeds_on_a_damaged_corpus(seed_advisors):
    """Reporting, not refusing. Reddens under: returning non-zero when findings exist —
    which would lock the rebuild on this instance, where 12 records are already damaged.
    """
    seed_advisors("nexus-ceo")
    _session("2026-09-14-nexus-ceo-x.md", "advisor: nexus-ceo\nissues: [#26]")
    assert run_engine("memory", "index", "--now", "2026-09-15").returncode == 0


def test_a_clean_corpus_produces_no_report(seed_advisors):
    """Paired: a reporter that fired unconditionally would satisfy both tests above."""
    seed_advisors("nexus-ceo")
    _session("2026-09-14-nexus-ceo-x.md", "advisor: nexus-ceo\nissues: [26]")
    r = run_engine("memory", "index", "--now", "2026-09-15")
    assert "lost a value" not in r.stderr
    assert r.returncode == 0
