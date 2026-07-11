"""Tests for enginelib.filing._append_xref — audit A2 regression.

_append_xref used to do a truncating read/write_text round-trip:
    content = target.read_text(); target.write_text(content + line + "\n")
which loses the pre-existing content on a crash between the two calls. It now
builds the full new content first and writes it via enginelib.snapshot.snapshot_write
(tmp sibling + os.replace) — a single atomic operation.
"""
import logging
from pathlib import Path

from enginelib.filing import DecisionOpts, _append_xref, _dedupe_slug, file_decision

_DATE = "2026-04-22"


# --- #52: slug-stutter dedupe -------------------------------------------------

def test_dedupe_slug_strips_repeated_advisor_prefix():
    assert _dedupe_slug("sage-cto", "sage-cto-first-launch") == "first-launch"


def test_dedupe_slug_noop_when_no_stutter():
    assert _dedupe_slug("kai-cto", "move-to-base") == "move-to-base"


def test_dedupe_slug_only_strips_full_prefix_token():
    # Slug equal to the advisor (no suffix) is left intact — stripping would empty it.
    assert _dedupe_slug("sage-cto", "sage-cto") == "sage-cto"
    # A different advisor whose id isn't a prefix must not be stripped.
    assert _dedupe_slug("cto", "sage-cto-x") == "sage-cto-x"


def test_dedupe_slug_empty_advisor_is_noop():
    assert _dedupe_slug("", "anything") == "anything"


def test_append_xref_preserves_pre_existing_content_and_no_tmp_leftover(tmp_path):
    target = tmp_path / "meeting.md"
    target.write_text("# Weekly Meeting\n\nSome pre-existing notes.\n")

    _append_xref(target, "../decisions/2026-04-22-kai-cto-x.md", "2026-04-22", "kai-cto", "x")

    content = target.read_text()
    # Pre-existing content must survive — proves the write was not a truncate-first op.
    assert "# Weekly Meeting" in content
    assert "Some pre-existing notes." in content
    assert "- Decision: [2026-04-22-kai-cto-x](../decisions/2026-04-22-kai-cto-x.md)" in content

    leftovers = list(tmp_path.glob("*.tmp.*"))
    assert leftovers == [], f"tmp files left behind: {leftovers}"


def test_append_xref_idempotent_skips_duplicate(tmp_path):
    target = tmp_path / "session.md"
    target.write_text("# Session\n")

    _append_xref(target, "../decisions/2026-04-22-kai-cto-x.md", "2026-04-22", "kai-cto", "x")
    first = target.read_text()
    _append_xref(target, "../decisions/2026-04-22-kai-cto-x.md", "2026-04-22", "kai-cto", "x")
    second = target.read_text()

    assert first == second
    assert first.count("- Decision:") == 1


def test_append_xref_routes_through_snapshot_write(tmp_path, monkeypatch):
    """Spy proof that _append_xref delegates its write to the atomic primitive."""
    import enginelib.filing as filing_mod

    calls = []
    real_snapshot_write = filing_mod.snapshot_write

    def spy(path, body):
        calls.append((path, body))
        return real_snapshot_write(path, body)

    monkeypatch.setattr(filing_mod, "snapshot_write", spy)

    target = tmp_path / "meeting.md"
    target.write_text("# Meeting\n")
    _append_xref(target, "../decisions/2026-04-22-kai-cto-x.md", "2026-04-22", "kai-cto", "x")

    assert len(calls) == 1
    assert calls[0][0] == target
    assert "# Meeting" in calls[0][1]


def test_hot_append_failure_is_non_fatal_and_unexpected_error_is_logged(
    seed_advisors, tmp_path, monkeypatch, caplog
):
    """Pattern A (hot.append best-effort, audit A3).

    An expected failure (ImportError/OSError, e.g. hot.md missing or a deferred
    import failure) stays quiet and non-fatal — the decision file is still written.
    An unexpected failure (e.g. a TypeError — a programming bug) is ALSO still
    non-fatal, but is now surfaced as a WARNING instead of silently discarded.
    """
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    import enginelib.memory.hot as hot_mod

    body = tmp_path / "body.md"
    body.write_text("Body.\n")

    caplog.set_level(logging.WARNING, logger="enginelib.filing")

    # Expected failure (OSError) — swallowed quietly; decision file still written.
    monkeypatch.setattr(
        hot_mod, "append", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
    )
    out1 = file_decision(
        DecisionOpts(slug="expected", by="nexus-ceo", date=_DATE, body_file=str(body))
    )
    assert Path(out1).is_file()
    assert not any(r.levelname == "WARNING" for r in caplog.records)

    # Unexpected failure (TypeError) — still non-fatal, but now logged as WARNING.
    caplog.clear()
    monkeypatch.setattr(
        hot_mod, "append", lambda *a, **k: (_ for _ in ()).throw(TypeError("bug"))
    )
    out2 = file_decision(
        DecisionOpts(slug="unexpected", by="nexus-ceo", date=_DATE, body_file=str(body))
    )
    assert Path(out2).is_file()
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_briefing_regen_failure_is_non_fatal_and_unexpected_error_is_logged(
    seed_advisors, tmp_path, monkeypatch, caplog
):
    """Pattern B (briefing regen with fd redirection, audit A3).

    An expected failure (ImportError/OSError, e.g. the fd dup2 dance) stays quiet
    and non-fatal — the decision file is still written. An unexpected failure
    (e.g. a TypeError raised from inside regen_advisor) is ALSO still non-fatal,
    but is now surfaced as a WARNING. The inner try/finally that restores the
    redirected stdout fd is untouched by this change either way.
    """
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    import briefing.regen as regen_mod

    body = tmp_path / "body.md"
    body.write_text("Body.\n")

    caplog.set_level(logging.WARNING, logger="enginelib.filing")

    # Expected failure (OSError) — swallowed quietly; decision file still written.
    monkeypatch.setattr(
        regen_mod, "regen_advisor", lambda *a, **k: (_ for _ in ()).throw(OSError("fd issue"))
    )
    out1 = file_decision(
        DecisionOpts(slug="expected-b", by="nexus-ceo", date=_DATE, body_file=str(body))
    )
    assert Path(out1).is_file()
    assert not any(r.levelname == "WARNING" for r in caplog.records)

    # Unexpected failure (TypeError) — still non-fatal, but now logged as WARNING.
    caplog.clear()
    monkeypatch.setattr(
        regen_mod, "regen_advisor", lambda *a, **k: (_ for _ in ()).throw(TypeError("bug"))
    )
    out2 = file_decision(
        DecisionOpts(slug="unexpected-b", by="nexus-ceo", date=_DATE, body_file=str(body))
    )
    assert Path(out2).is_file()
    assert any(r.levelname == "WARNING" for r in caplog.records)
