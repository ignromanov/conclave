"""tests/cmd/test_lifecycle_archive_aged.py — integration tests for `engine lifecycle archive-aged`.

Hermetic: bare tmp_path (NOT ai_root). Uses CONCLAVE_AI_ROOT seam for run-log isolation.
Port of engine/scripts/tests/lifecycle/archive-aged.bats (8 cases).
"""
from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from tests.cmd.helpers import run_engine


def _write_md(path: Path, tags_line: str, body: str = "body text") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntype: note\nschema_version: 1\n{tags_line}\nid: test\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def _set_age(path: Path, days: float) -> None:
    t = time.time() - days * 86400
    os.utime(path, (t, t))


# ---------------------------------------------------------------------------
# 1. Transition: resolved+old → archived; resolved+recent → unchanged; open+old → unchanged
# ---------------------------------------------------------------------------
def test_transition(tmp_path):
    tree = tmp_path / "vault"
    a = _write_md(tree / "A.md", "tags: [status/resolved]", body="[[some-link]]")
    b = _write_md(tree / "B.md", "tags: [status/resolved]")
    c = _write_md(tree / "C.md", "tags: [status/open]")
    _set_age(a, 40)
    _set_age(b, 5)
    _set_age(c, 40)

    r = run_engine("lifecycle", "archive-aged", "--root", str(tree))
    assert r.returncode == 0

    # A: was status/resolved + 40 days old → must now be status/archived
    assert "status/archived" in a.read_text(encoding="utf-8")
    assert "status/resolved" not in a.read_text(encoding="utf-8")

    # B: was status/resolved + 5 days old → unchanged (still status/resolved)
    assert "status/resolved" in b.read_text(encoding="utf-8")
    assert "status/archived" not in b.read_text(encoding="utf-8")

    # C: was status/open + 40 days old → unchanged (still status/open)
    assert "status/open" in c.read_text(encoding="utf-8")
    assert "status/archived" not in c.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. Idempotent: re-run leaves already-archived files unchanged; count = 0
# ---------------------------------------------------------------------------
def test_idempotent(tmp_path):
    tree = tmp_path / "vault"
    a = _write_md(tree / "A.md", "tags: [status/resolved]")
    b = _write_md(tree / "B.md", "tags: [status/resolved]")
    c = _write_md(tree / "C.md", "tags: [status/open]")
    _set_age(a, 40)
    _set_age(b, 5)
    _set_age(c, 40)

    r1 = run_engine("lifecycle", "archive-aged", "--root", str(tree))
    assert r1.returncode == 0

    before = a.read_text(encoding="utf-8")

    r2 = run_engine("lifecycle", "archive-aged", "--root", str(tree))
    assert r2.returncode == 0

    assert a.read_text(encoding="utf-8") == before
    assert "archived 0" in r2.stdout


# ---------------------------------------------------------------------------
# 3. --dry-run: WOULD ARCHIVE printed; file byte-identical
# ---------------------------------------------------------------------------
def test_dry_run(tmp_path):
    tree = tmp_path / "vault"
    a = _write_md(tree / "A.md", "tags: [status/resolved]")
    b = _write_md(tree / "B.md", "tags: [status/resolved]")
    c = _write_md(tree / "C.md", "tags: [status/open]")
    _set_age(a, 40)
    _set_age(b, 5)
    _set_age(c, 40)

    before = a.read_text(encoding="utf-8")

    r = run_engine("lifecycle", "archive-aged", "--root", str(tree), "--dry-run")
    assert r.returncode == 0
    assert "WOULD ARCHIVE" in r.stdout
    assert "A.md" in r.stdout

    assert a.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# 4. --age-days threshold: 10-day file not archived at 30, archived at 7
# ---------------------------------------------------------------------------
def test_age_days_threshold(tmp_path):
    tree = tmp_path / "vault2"
    x = _write_md(tree / "X.md", "tags: [status/resolved]")
    _set_age(x, 10)

    # Default threshold = 30 → should NOT archive
    r = run_engine("lifecycle", "archive-aged", "--root", str(tree))
    assert r.returncode == 0
    assert "status/resolved" in x.read_text(encoding="utf-8")
    assert "status/archived" not in x.read_text(encoding="utf-8")

    # Threshold = 7 → should archive
    r2 = run_engine("lifecycle", "archive-aged", "--root", str(tree), "--age-days", "7")
    assert r2.returncode == 0
    assert "status/archived" in x.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 5. Wikilinks in file body preserved after tag swap (B23 invariant)
# ---------------------------------------------------------------------------
def test_wikilinks_preserved(tmp_path):
    tree = tmp_path / "vault"
    a = _write_md(tree / "A.md", "tags: [status/resolved]", body="See [[some-link]] for details.")
    _set_age(a, 40)

    r = run_engine("lifecycle", "archive-aged", "--root", str(tree))
    assert r.returncode == 0
    assert "[[some-link]]" in a.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 6. Other tags preserved on the tags: line
# ---------------------------------------------------------------------------
def test_other_tags_preserved(tmp_path):
    tree = tmp_path / "vault3"
    m = tree / "multi.md"
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(
        "---\ntype: audit-finding\nschema_version: 1\n"
        "tags: [op/audit-finding, status/resolved, priority/p1]\n"
        "id: multi-tag-test\n---\n\nbody text\n",
        encoding="utf-8",
    )
    _set_age(m, 40)

    r = run_engine("lifecycle", "archive-aged", "--root", str(tree))
    assert r.returncode == 0

    content = m.read_text(encoding="utf-8")
    assert "op/audit-finding" in content
    assert "status/archived" in content
    assert "priority/p1" in content
    assert "status/resolved" not in content


# ---------------------------------------------------------------------------
# 7. Run-log row appended with archived=N (exercises dispatcher run-log args hook)
# ---------------------------------------------------------------------------
def test_run_log_archived_count(tmp_path):
    tree = tmp_path / "vault4"
    for name in ("one.md", "two.md"):
        f = _write_md(tree / name, "tags: [status/resolved]")
        _set_age(f, 40)

    today = datetime.now(UTC).date().isoformat()
    log_path = tmp_path / "agent-memory" / "run-log" / f"{today}.jsonl"

    before_lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []

    r = run_engine(
        "lifecycle", "archive-aged", "--root", str(tree),
        env={"CONCLAVE_AI_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0

    assert log_path.exists()
    after_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(after_lines) > len(before_lines)

    new_lines = after_lines[len(before_lines):]
    assert any("archived=2" in line for line in new_lines)


# ---------------------------------------------------------------------------
# 8. Missing root: exit 1 + stderr contains the path
# ---------------------------------------------------------------------------
def test_missing_root(tmp_path):
    r = run_engine("lifecycle", "archive-aged", "--root", "/nonexistent/vault")
    assert r.returncode == 1
    assert "/nonexistent/vault" in r.stderr
