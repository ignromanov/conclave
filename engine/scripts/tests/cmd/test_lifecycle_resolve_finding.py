"""tests/cmd/test_lifecycle_resolve_finding.py — integration tests for `engine lifecycle resolve-finding`.

Hermetic: bare tmp_path (NOT ai_root). Uses CONCLAVE_AI_ROOT seam for run-log isolation.
Port of engine/scripts/tests/lifecycle/resolve-finding.bats (8 cases).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tests.cmd.helpers import run_engine


def _open_finding(path: Path) -> Path:
    """Write a status/open audit-finding fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: audit-finding\n"
        "schema_version: 1\n"
        "tags: [op/audit-finding, status/open, priority/p1]\n"
        "id: test-finding\n"
        "---\n\n"
        "Something needs fixing.\n",
        encoding="utf-8",
    )
    return path


def _no_tags_finding(path: Path) -> Path:
    """Write a finding fixture with neither status/open nor status/resolved."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: audit-finding\n"
        "schema_version: 1\n"
        "tags: [op/audit-finding, priority/p1]\n"
        "id: test-no-status\n"
        "---\n\n"
        "Missing status tag.\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# 1. Transition: status/open → status/resolved with Resolution block.
# ---------------------------------------------------------------------------
def test_transition(tmp_path):
    finding = _open_finding(tmp_path / "finding.md")

    r = run_engine("lifecycle", "resolve-finding", str(finding), "--note", "fixed in commit X")
    assert r.returncode == 0

    content = finding.read_text(encoding="utf-8")
    assert "status/resolved" in content
    assert not any(
        line.startswith("tags:") and "status/open" in line
        for line in content.splitlines()
    )
    assert "## Resolution" in content
    assert "fixed in commit X" in content


# ---------------------------------------------------------------------------
# 2. Idempotent: same note → byte-identical file on second run.
# ---------------------------------------------------------------------------
def test_idempotent_same_note(tmp_path):
    finding = _open_finding(tmp_path / "finding.md")

    r1 = run_engine("lifecycle", "resolve-finding", str(finding), "--note", "fixed in commit abc")
    assert r1.returncode == 0

    before = finding.read_bytes()

    r2 = run_engine("lifecycle", "resolve-finding", str(finding), "--note", "fixed in commit abc")
    assert r2.returncode == 0

    assert finding.read_bytes() == before


# ---------------------------------------------------------------------------
# 3. Different note replaces Resolution body (not appends).
# ---------------------------------------------------------------------------
def test_different_note_replaces(tmp_path):
    finding = _open_finding(tmp_path / "finding.md")

    r1 = run_engine("lifecycle", "resolve-finding", str(finding), "--note", "note A")
    assert r1.returncode == 0

    r2 = run_engine("lifecycle", "resolve-finding", str(finding), "--note", "note B")
    assert r2.returncode == 0

    content = finding.read_text(encoding="utf-8")
    assert "note B" in content
    assert "note A" not in content
    assert content.count("## Resolution") == 1


# ---------------------------------------------------------------------------
# 4. Exits 1 when file lacks status/open (or status/resolved) tag.
# ---------------------------------------------------------------------------
def test_lacks_status_open(tmp_path):
    finding = _no_tags_finding(tmp_path / "finding.md")

    r = run_engine("lifecycle", "resolve-finding", str(finding), "--note", "some fix")
    assert r.returncode == 1
    assert "status/open" in r.stderr


# ---------------------------------------------------------------------------
# 5. Exits 1 when file does not exist.
# ---------------------------------------------------------------------------
def test_file_not_found(tmp_path):
    r = run_engine(
        "lifecycle", "resolve-finding",
        "/nonexistent/path/finding.md",
        "--note", "x",
    )
    assert r.returncode == 1
    assert "not found" in r.stderr


# ---------------------------------------------------------------------------
# 6. Exits 1 when --note is missing.
# ---------------------------------------------------------------------------
def test_note_missing(tmp_path):
    finding = _open_finding(tmp_path / "finding.md")

    r = run_engine("lifecycle", "resolve-finding", str(finding))
    assert r.returncode == 1
    assert "usage" in r.stderr


# ---------------------------------------------------------------------------
# 7. Run-log row appended; script field = "engine lifecycle resolve-finding".
# ---------------------------------------------------------------------------
def test_run_log_row(tmp_path):
    finding = _open_finding(tmp_path / "finding.md")

    today = datetime.now(UTC).date().isoformat()
    log_path = tmp_path / "agent-memory" / "run-log" / f"{today}.jsonl"

    before_lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []

    r = run_engine(
        "lifecycle", "resolve-finding", str(finding), "--note", "test row",
        env={"CONCLAVE_AI_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0

    assert log_path.exists()
    after_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(after_lines) > len(before_lines)

    new_lines = after_lines[len(before_lines):]
    parsed = [json.loads(line) for line in new_lines]
    assert any(row.get("script") == "engine lifecycle resolve-finding" for row in parsed)


# ---------------------------------------------------------------------------
# 8. Other tags preserved after transition.
# ---------------------------------------------------------------------------
def test_other_tags_preserved(tmp_path):
    finding = _open_finding(tmp_path / "finding.md")

    r = run_engine("lifecycle", "resolve-finding", str(finding), "--note", "preserve tags test")
    assert r.returncode == 0

    content = finding.read_text(encoding="utf-8")
    assert "op/audit-finding" in content
    assert "priority/p1" in content
    assert "status/resolved" in content
    assert "status/open" not in content
