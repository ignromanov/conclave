"""tests/cmd/test_lifecycle_archive_handoff.py — tests for `engine lifecycle archive-handoff`.

Hermetic: bare tmp_path (NOT ai_root), driving the handoffs dir through --handoffs-dir
the way test_lifecycle_archive_aged.py drives --root.

#55: a handoff had no terminal state. ops/handoffs/archive/ already existed and
session_init's resume-scan already ignored it (its glob is non-recursive), but nothing
ever moved an exhausted handoff there, so resume-scan resurfaced shipped work forever —
15 of them for forge, the oldest 460h old.

Terminal state is therefore the file's LOCATION, and the transition is a move: reversible,
never a delete.
"""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine


def _write_handoff(d: Path, name: str, body: str = "## Status: DONE\n") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(f"# Handoff: {name}\n\n> **From**: forge | **To**: next session\n\n{body}", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Move: named handoff lands in archive/ and leaves the live dir
# ---------------------------------------------------------------------------
def test_archives_named_handoff(tmp_path):
    d = tmp_path / "handoffs"
    h = _write_handoff(d, "2026-07-09-forge-charter-shipped.md")
    before = h.read_text(encoding="utf-8")

    r = run_engine("lifecycle", "archive-handoff", h.name, "--handoffs-dir", str(d))
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"

    assert not h.exists(), "handoff still in the live dir"
    archived = d / "archive" / h.name
    assert archived.is_file(), "handoff did not land in archive/"
    assert archived.read_text(encoding="utf-8") == before, "content changed during the move"


# ---------------------------------------------------------------------------
# 2. The point of the whole exercise: resume-scan stops surfacing it
# ---------------------------------------------------------------------------
def test_archived_handoff_leaves_resume_scan(tmp_path):
    """session_init's resume-scan reads ops/handoffs/ non-recursively."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lifecycle"))
    from session_init import _step1b_resume_scan

    root = tmp_path / "data"
    d = root / "ops" / "handoffs"
    h = _write_handoff(d, "2026-07-09-forge-charter-shipped.md")

    found_before, _ = _step1b_resume_scan("forge", root)
    assert any(h.name in line for line in found_before), "setup: handoff not surfaced before archiving"

    r = run_engine("lifecycle", "archive-handoff", h.name, "--handoffs-dir", str(d))
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"

    found_after, _ = _step1b_resume_scan("forge", root)
    assert not any(h.name in line for line in found_after), "archived handoff still resurfaces"


# ---------------------------------------------------------------------------
# 3. Refuse to clobber an already-archived file
# ---------------------------------------------------------------------------
def test_refuses_to_overwrite_archived(tmp_path):
    d = tmp_path / "handoffs"
    name = "2026-07-09-forge-charter-shipped.md"
    live = _write_handoff(d, name, body="## Status: LIVE\n")
    already = _write_handoff(d / "archive", name, body="## Status: ARCHIVED EARLIER\n")
    preserved = already.read_text(encoding="utf-8")

    r = run_engine("lifecycle", "archive-handoff", name, "--handoffs-dir", str(d))
    assert r.returncode == 1
    assert name in r.stderr
    assert live.is_file(), "live handoff was moved despite the collision"
    assert already.read_text(encoding="utf-8") == preserved, "archived copy was overwritten"


# ---------------------------------------------------------------------------
# 4. Unknown name → exit 1, name echoed
# ---------------------------------------------------------------------------
def test_unknown_handoff_exit1(tmp_path):
    d = tmp_path / "handoffs"
    d.mkdir(parents=True)

    r = run_engine("lifecycle", "archive-handoff", "no-such-handoff.md", "--handoffs-dir", str(d))
    assert r.returncode == 1
    assert "no-such-handoff.md" in r.stderr


# ---------------------------------------------------------------------------
# 5. --dry-run reports without moving
# ---------------------------------------------------------------------------
def test_dry_run(tmp_path):
    d = tmp_path / "handoffs"
    h = _write_handoff(d, "2026-07-13-forge-104-post-signoff.md")

    r = run_engine("lifecycle", "archive-handoff", h.name, "--handoffs-dir", str(d), "--dry-run")
    assert r.returncode == 0
    assert "WOULD ARCHIVE" in r.stdout
    assert h.name in r.stdout
    assert h.is_file(), "--dry-run moved the file"
    assert not (d / "archive" / h.name).exists()


# ---------------------------------------------------------------------------
# 6. A name is a name, not a path — no escaping the handoffs dir
# ---------------------------------------------------------------------------
def test_rejects_path_traversal(tmp_path):
    d = tmp_path / "handoffs"
    d.mkdir(parents=True)
    outside = tmp_path / "secret.md"
    outside.write_text("do not move me\n", encoding="utf-8")

    r = run_engine("lifecycle", "archive-handoff", "../secret.md", "--handoffs-dir", str(d))
    assert r.returncode == 1
    assert outside.is_file(), "traversal moved a file outside the handoffs dir"


# ---------------------------------------------------------------------------
# 7. Several handoffs in one call — the backlog case
# ---------------------------------------------------------------------------
def test_archives_several(tmp_path):
    d = tmp_path / "handoffs"
    names = [
        "2026-07-09-forge-charter-shipped.md",
        "2026-07-10-forge-103-w2-fresh-history-build.md",
        "2026-07-13-forge-104-post-signoff.md",
    ]
    for n in names:
        _write_handoff(d, n)

    r = run_engine("lifecycle", "archive-handoff", *names, "--handoffs-dir", str(d))
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"

    for n in names:
        assert not (d / n).exists(), f"{n} still live"
        assert (d / "archive" / n).is_file(), f"{n} missing from archive/"


# ---------------------------------------------------------------------------
# 8. #55 — until someone archives it, an exhausted handoff must not read as live work
# ---------------------------------------------------------------------------
def _resume_scan(advisor: str, root: Path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lifecycle"))
    from session_init import _step1b_resume_scan
    return _step1b_resume_scan(advisor, root)


def test_an_untouched_handoff_is_demoted_to_stale(tmp_path):
    """archive-handoff gives handoffs a terminal state, but nothing invokes it, and the
    scan ranks by mtime alone — two handoffs were surfacing as interrupted work at 1374h
    and 1226h, both tracking PRs merged in July. Age stands in for the consumed-state the
    format still lacks.
    """
    import os
    import time

    root = tmp_path / "data"
    d = root / "ops" / "handoffs"
    old = _write_handoff(d, "2026-07-09-forge-shipped-in-july.md")
    fresh = _write_handoff(d, "2026-08-30-forge-still-live.md")
    ancient = time.time() - 400 * 3600
    os.utime(old, (ancient, ancient))

    live, stale = _resume_scan("forge", root)
    assert any(fresh.name in ln for ln in live), "a fresh handoff must still read as live"
    assert not any(old.name in ln for ln in live), "400h handoff still presented as live work"
    assert any(old.name in ln for ln in stale), "stale handoff was dropped, not demoted"


def test_the_stale_threshold_is_operator_settable(tmp_path):
    """A long-running thread is a real thing; the default must be raisable, not a wall."""
    import os
    import time

    root = tmp_path / "data"
    d = root / "ops" / "handoffs"
    h = _write_handoff(d, "2026-07-09-forge-slow-but-live.md")
    ancient = time.time() - 400 * 3600
    os.utime(h, (ancient, ancient))

    os.environ["CONCLAVE_HANDOFF_STALE_HOURS"] = "1000"
    try:
        live, stale = _resume_scan("forge", root)
    finally:
        del os.environ["CONCLAVE_HANDOFF_STALE_HOURS"]
    assert any(h.name in ln for ln in live)
    assert not stale
