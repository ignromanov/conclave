"""tests/enginelib/test_hot_compaction_archive.py — compaction may cap, never discard (#139).

`hot.md` is a live buffer with a word budget, so capping `Recent decisions` is
correct. Discarding what it caps is not — see VISION §6 — and the capped list was
implemented as plain truncation — `rd[-5:]` with the head
dropped on the floor and no return channel, so `append()` had nothing to preserve
and nothing to report.

Two distinct losses, and the second is the one the title never mentioned:

  * bullets beyond the cap — bounded, expected, still unrecorded;
  * *any* non-bullet line inside the section (a note, a sub-item, a paragraph) —
    unbounded, no cap involved, eaten by the `continue` that skips non-bullets.

Observed live: `engine session close` for keel-coo on 2026-09-08 added one
decision and dropped one, with no archive line and nothing on stderr — the
closing session had no way to know it had evicted anything.

Bare tmp_path as CONCLAVE_AI_ROOT; per-test LOCK_DIR keeps the lock hermetic
under pytest-xdist. The advisor is deliberately non-canonical ("kai"), so
append()'s best-effort briefing regen is skipped and the test measures compaction
rather than the briefing layer.
"""
from __future__ import annotations

import logging

import pytest

from enginelib.memory import hot

# Enough words elsewhere in the file to hold it over the 500-word compaction
# trigger no matter how few bullets survive in Recent decisions — so compaction
# is guaranteed to fire on the next append, deterministically, without needing
# dozens of them. This mirrors the live instance, where Open threads is grow-only
# and has kept hot.md permanently over budget.
_FILLER = "\n".join(
    f"- [2026-09-0{i % 9 + 1}T00:00-0300] kai: open thread {i} "
    "carrying enough words to keep this file over its compaction budget"
    for i in range(1, 31)
)


def _hot_body(decisions: list[str]) -> str:
    return (
        "# Hot — live memory\n\n"
        "## Now\n\n- (none)\n\n"
        f"## Open threads\n\n{_FILLER}\n\n"
        "## Recent decisions\n\n" + "\n".join(decisions) + "\n\n"
        "## Watch\n\n- (none)\n\n"
        "## Last updated\n\n2026-09-08T00:00-0300 by test\n"
    )


@pytest.fixture()
def instance(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    monkeypatch.setenv("LOCK_DIR", str(tmp_path / "locks"))
    mem = tmp_path / "agent-memory"
    mem.mkdir(parents=True, exist_ok=True)
    return mem


def _decisions(n: int) -> list[str]:
    return [f"- [2026-09-08T0{i}:00-0300] kai: decision-{i} → decisions/d{i}.md" for i in range(1, n + 1)]


# --- unit: the compactor reports what it removed -------------------------


def test_compact_text_returns_the_lines_it_removed():
    """The root cause is the missing return channel, so assert the channel itself.

    Truncating in place and returning only the new body leaves the caller unable
    to archive or report — no amount of care at the call site can recover a line
    the compactor already dropped.
    """
    body = _hot_body(_decisions(8))
    compacted, evicted = hot._compact_text(body)

    assert [e.split("kai: ")[1].split(" →")[0] for e in evicted] == [
        "decision-1", "decision-2", "decision-3"
    ], f"evicted list is wrong: {evicted}"
    for line in evicted:
        assert line not in compacted, f"reported evicted but still present: {line}"


def test_compact_text_reports_non_bullet_content_too():
    """The unbounded half: a note inside the section dies with no cap involved."""
    body = _hot_body(_decisions(2) + ["  a hand-written note under a decision"])
    compacted, evicted = hot._compact_text(body)

    assert "  a hand-written note under a decision" in evicted, (
        f"non-bullet content vanished unreported: {evicted}"
    )
    assert "a hand-written note" not in compacted


def test_compact_text_evicts_nothing_when_under_the_cap():
    body = _hot_body(_decisions(3))
    compacted, evicted = hot._compact_text(body)

    assert evicted == []
    for line in _decisions(3):
        assert line in compacted


# --- integration: eviction is durable and announced ----------------------


def test_evicted_decisions_are_archived_before_they_are_dropped(instance):
    (instance / "hot.md").write_text(_hot_body(_decisions(8)), encoding="utf-8")

    hot.append("recent-decisions", "kai", "decision-9 → decisions/d9.md")

    archive = (instance / "hot-archive.md").read_text(encoding="utf-8")
    for slug in ("decision-1", "decision-2", "decision-3", "decision-4"):
        assert slug in archive, f"{slug} was evicted from hot.md and archived nowhere:\n{archive}"

    live = (instance / "hot.md").read_text(encoding="utf-8")
    assert "decision-9" in live
    assert "decision-1 " not in live, "cap did not apply — this test is not measuring compaction"


def test_eviction_is_announced_not_silent(instance, caplog):
    """The rule has two halves: the data survives *and* someone is told.

    An archive nobody is told about is still a silent event to the session that
    caused it — which is exactly how a keel-coo close evicted a sage-cto decision
    without either advisor learning of it.
    """
    (instance / "hot.md").write_text(_hot_body(_decisions(8)), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="enginelib.memory.hot"):
        hot.append("recent-decisions", "kai", "decision-9 → decisions/d9.md")

    assert any("evicted" in r.getMessage() for r in caplog.records), (
        f"compaction dropped lines and said nothing: {[r.getMessage() for r in caplog.records]}"
    )


def test_no_eviction_writes_no_archive(instance):
    """Silence is correct when nothing was removed — no empty file, no noise."""
    (instance / "hot.md").write_text(_hot_body(_decisions(2)), encoding="utf-8")

    hot.append("recent-decisions", "kai", "decision-3 → decisions/d3.md")

    assert not (instance / "hot-archive.md").exists()


def test_archive_accumulates_across_compactions(instance):
    """Additive: a second eviction must not overwrite the first one's record."""
    (instance / "hot.md").write_text(_hot_body(_decisions(8)), encoding="utf-8")

    hot.append("recent-decisions", "kai", "decision-9 → decisions/d9.md")
    first = (instance / "hot-archive.md").read_text(encoding="utf-8")
    hot.append("recent-decisions", "kai", "decision-10 → decisions/d10.md")
    second = (instance / "hot-archive.md").read_text(encoding="utf-8")

    assert first in second, "the archive was rewritten, not appended to"
    assert "decision-4" in second and "decision-5" in second


def test_a_failed_archive_write_leaves_hot_md_intact(instance):
    """Order is the invariant: archive first, truncate second — never the reverse.

    If the archive write can fail *after* hot.md has been truncated, the crash
    window is precisely the data loss this whole guard exists to prevent. Made
    observable by putting a directory where the archive file belongs, so the
    archive write raises and nothing else does.
    """
    before = _hot_body(_decisions(8))
    (instance / "hot.md").write_text(before, encoding="utf-8")
    (instance / "hot-archive.md").mkdir()

    with pytest.raises(OSError):
        hot.append("recent-decisions", "kai", "decision-9 → decisions/d9.md")

    after = (instance / "hot.md").read_text(encoding="utf-8")
    for slug in ("decision-1", "decision-2", "decision-3", "decision-4"):
        assert slug in after, (
            f"{slug} was truncated out of hot.md even though its archive write failed:\n{after}"
        )
