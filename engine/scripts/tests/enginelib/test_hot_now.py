"""tests/enginelib/test_hot_now.py — the Now section's add/remove lifecycle (#149).

Now holds sessions that are open *right now*: session_init appends a line when a
session opens, close_session removes that same line when it closes. That needs a
remove() counterpart to append(), and it needs both to manage the placeholder
bullet the template seeds each section with — otherwise a populated section still
renders "- (waiting for first append)" above its real entries, which is the
symptom #149 was filed for.

Bare tmp_path as CONCLAVE_AI_ROOT; per-test LOCK_DIR keeps the lock hermetic
under pytest-xdist.
"""
from __future__ import annotations

import pytest

from enginelib.memory import hot


@pytest.fixture()
def hot_md(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    monkeypatch.setenv("LOCK_DIR", str(tmp_path / "locks"))
    hot.init(hot_path=tmp_path / "agent-memory" / "hot.md")
    return tmp_path / "agent-memory" / "hot.md"


def _section(text: str, header: str) -> list[str]:
    """Bullet lines under `header`, up to the next '## ' header."""
    out: list[str] = []
    inside = False
    for line in text.split("\n"):
        if line == header:
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside and line.startswith("- "):
            out.append(line)
    return out


# --- placeholder handling ------------------------------------------------


def test_append_drops_the_placeholder_bullet(hot_md):
    """A real entry replaces '- (waiting for first append)', it does not join it."""
    hot.append("now", "forge-chro", "149-hot-now-producer")

    bullets = _section(hot_md.read_text(encoding="utf-8"), "## Now")
    assert len(bullets) == 1, f"placeholder survived alongside the entry: {bullets}"
    assert "149-hot-now-producer" in bullets[0]
    assert "waiting for first append" not in hot_md.read_text(encoding="utf-8")


def test_append_drops_the_none_placeholder_in_other_sections(hot_md):
    """Same rule for the '- (none)' sections — Watch shipped this defect live."""
    hot.append("watch", "sage-cto", "something to watch")

    bullets = _section(hot_md.read_text(encoding="utf-8"), "## Watch")
    assert bullets == [b for b in bullets if "(none)" not in b]
    assert len(bullets) == 1


# --- remove --------------------------------------------------------------


def test_remove_deletes_the_matching_entry(hot_md):
    hot.append("now", "forge-chro", "session-a")
    hot.append("now", "sage-cto", "session-b")

    removed = hot.remove("now", "forge-chro", "session-a")

    assert removed == 1
    bullets = _section(hot_md.read_text(encoding="utf-8"), "## Now")
    assert len(bullets) == 1
    assert "session-b" in bullets[0]
    assert "session-a" not in hot_md.read_text(encoding="utf-8")


def test_remove_matches_on_advisor_and_content_together(hot_md):
    """Two advisors on the same slug must not remove each other's line."""
    hot.append("now", "forge-chro", "shared-slug")
    hot.append("now", "sage-cto", "shared-slug")

    hot.remove("now", "forge-chro", "shared-slug")

    bullets = _section(hot_md.read_text(encoding="utf-8"), "## Now")
    assert len(bullets) == 1
    assert "sage-cto" in bullets[0]


def test_remove_is_a_noop_when_nothing_matches(hot_md):
    hot.append("now", "forge-chro", "session-a")
    before = hot_md.read_text(encoding="utf-8")

    removed = hot.remove("now", "keel-coo", "never-opened")

    assert removed == 0
    assert hot_md.read_text(encoding="utf-8") == before


def test_remove_restores_the_placeholder_when_the_section_empties(hot_md):
    """An empty section must not collapse into a headerless blank."""
    hot.append("now", "forge-chro", "only-session")
    hot.remove("now", "forge-chro", "only-session")

    text = hot_md.read_text(encoding="utf-8")
    assert "## Now" in text
    bullets = _section(text, "## Now")
    assert len(bullets) == 1
    assert "(none)" in bullets[0] or "waiting" in bullets[0]


def test_remove_rejects_an_invalid_section(hot_md):
    with pytest.raises(ValueError, match="invalid section"):
        hot.remove("nonesuch", "forge-chro", "x")


def test_remove_leaves_other_sections_untouched(hot_md):
    hot.append("now", "forge-chro", "open-one")
    hot.append("open-threads", "forge-chro", "closed something")
    hot.append("recent-decisions", "forge-chro", "a decision")

    hot.remove("now", "forge-chro", "open-one")

    text = hot_md.read_text(encoding="utf-8")
    assert len(_section(text, "## Open threads")) == 1
    assert len(_section(text, "## Recent decisions")) == 1
    assert "closed something" in text
    assert "a decision" in text


# --- the round trip the producer actually performs -----------------------


def test_open_then_close_leaves_now_empty_again(hot_md):
    """The full session lifecycle: Now grows on open and shrinks on close."""
    hot.append("now", "forge-chro", "149-hot-now-producer")
    assert len(_section(hot_md.read_text(encoding="utf-8"), "## Now")) == 1

    hot.remove("now", "forge-chro", "149-hot-now-producer")

    bullets = _section(hot_md.read_text(encoding="utf-8"), "## Now")
    assert len(bullets) == 1
    assert "149-hot-now-producer" not in bullets[0]


def test_two_concurrent_sessions_both_show_then_drain(hot_md):
    hot.append("now", "forge-chro", "task-a")
    hot.append("now", "sage-cto", "task-b")
    assert len(_section(hot_md.read_text(encoding="utf-8"), "## Now")) == 2

    hot.remove("now", "sage-cto", "task-b")
    hot.remove("now", "forge-chro", "task-a")

    bullets = _section(hot_md.read_text(encoding="utf-8"), "## Now")
    assert len(bullets) == 1
    assert "task-a" not in bullets[0] and "task-b" not in bullets[0]


def test_remove_does_not_double_the_placeholder_on_a_legacy_section(hot_md):
    """A pre-existing file can hold a placeholder AND real entries side by side.

    The live instance's Watch section is exactly that shape: `- (none)` was seeded at
    init and a real entry was appended below it without displacing it. Draining such a
    section must leave one placeholder, not the seeded one plus a fresh one.
    """
    text = hot_md.read_text(encoding="utf-8")
    text = text.replace(
        "## Watch\n\n- (none)\n",
        "## Watch\n\n- (none)\n- [2026-01-01T00:00+0000] sage-cto: legacy entry\n",
    )
    hot_md.write_text(text, encoding="utf-8")

    assert hot.remove("watch", "sage-cto", "legacy entry") == 1

    bullets = _section(hot_md.read_text(encoding="utf-8"), "## Watch")
    assert bullets == ["- (none)"], bullets


# --- supersede: an unclosed session is evidence, not litter (#229) --------
#
# Spec 117 R9: `/conclave:start` must not erase an unclosed Now entry; it may only
# mark it superseded. The measurement behind the rule: of 9 `session open` entries
# ever committed to this instance's Now, 4 vanished with no close — 44% — because
# session_init drained the section before re-registering.


def _open(advisor: str, token: str) -> None:
    hot.append("now", advisor, hot.session_open_line(token))


def test_supersede_moves_a_foreign_session_into_open_threads(hot_md):
    """The stale entry leaves Now, but it leaves *into* a grow-only section."""
    _open("sage-cto", "aaaaaaaa-1111")

    moved = hot.supersede_stale_session("sage-cto", "bbbbbbbb-2222")

    assert len(moved) == 1, f"the stale session was not detected: {moved}"
    text = hot_md.read_text(encoding="utf-8")
    assert _section(text, "## Now") == ["- (none)"]
    threads = _section(text, "## Open threads")
    assert len(threads) == 1, threads
    assert "never closed" in threads[0]
    assert "superseded at" in threads[0]


def test_supersede_preserves_the_original_timestamp_and_token(hot_md):
    """Age is the evidence: the entry keeps when it opened, not when it was found."""
    text = hot_md.read_text(encoding="utf-8").replace(
        "- (waiting for first append)",
        "- [2026-09-06T00:53-0300] sage-cto: session open (aaaaaaaa)",
    )
    hot_md.write_text(text, encoding="utf-8")

    hot.supersede_stale_session("sage-cto", "bbbbbbbb")

    threads = _section(hot_md.read_text(encoding="utf-8"), "## Open threads")
    assert threads[0].startswith("- [2026-09-06T00:53-0300] sage-cto: "), threads
    assert "aaaaaaaa" in threads[0]


def test_superseded_entry_is_out_of_reach_of_the_close_drain(hot_md):
    """close_session removes by the SESSION_OPEN substring. If the moved line still
    carried it, the next close would destroy the evidence a second time."""
    _open("sage-cto", "aaaaaaaa")
    hot.supersede_stale_session("sage-cto", "bbbbbbbb")

    threads = _section(hot_md.read_text(encoding="utf-8"), "## Open threads")
    assert hot.SESSION_OPEN not in threads[0], threads[0]


def test_supersede_leaves_the_same_session_alone(hot_md):
    """session-init runs twice per Claude session — hook, then the bound skill.
    Without the token check the second run would report the first as abandoned."""
    _open("sage-cto", "aaaaaaaa")
    before = hot_md.read_text(encoding="utf-8")

    assert hot.supersede_stale_session("sage-cto", "aaaaaaaa") == []
    assert hot_md.read_text(encoding="utf-8") == before


def test_supersede_leaves_another_advisor_alone(hot_md):
    _open("forge-chro", "aaaaaaaa")

    assert hot.supersede_stale_session("sage-cto", "bbbbbbbb") == []
    assert len(_section(hot_md.read_text(encoding="utf-8"), "## Now")) == 1


def test_supersede_without_a_token_does_nothing(hot_md):
    """No fencing token means the two sessions cannot be told apart, and a report
    that cannot be told apart from a false one is worse than no report."""
    _open("sage-cto", "")
    before = hot_md.read_text(encoding="utf-8")

    assert hot.supersede_stale_session("sage-cto", "") == []
    assert hot_md.read_text(encoding="utf-8") == before


def test_supersede_displaces_the_open_threads_placeholder(hot_md):
    _open("sage-cto", "aaaaaaaa")
    hot.supersede_stale_session("sage-cto", "bbbbbbbb")

    threads = _section(hot_md.read_text(encoding="utf-8"), "## Open threads")
    assert len(threads) == 1, f"placeholder survived beside the entry: {threads}"


def test_supersede_keeps_a_second_advisors_open_session_in_now(hot_md):
    _open("sage-cto", "aaaaaaaa")
    _open("forge-chro", "cccccccc")

    hot.supersede_stale_session("sage-cto", "bbbbbbbb")

    now = _section(hot_md.read_text(encoding="utf-8"), "## Now")
    assert len(now) == 1 and "forge-chro" in now[0], now


def test_session_open_line_carries_the_token(hot_md):
    line = hot.session_open_line("cc33884b-3e81-4b68-a6f8-b1b0460601c4")
    assert line.startswith(hot.SESSION_OPEN)
    assert "cc33884b" in line
    assert hot.session_open_line("") == hot.SESSION_OPEN
