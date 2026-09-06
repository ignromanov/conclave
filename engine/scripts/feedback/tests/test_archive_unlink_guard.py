"""test_archive_unlink_guard.py — the archiver refuses to unlink a review its own archive
row cannot reconstruct (conclave#152).

The whole-review path appends an archive row and then used to unlink the source markdown
unconditionally. Once the markdown is gone the row IS the record; if the row itself cannot
stand in for the item bodies it just described, unlinking destroys them unrecoverably. These
tests exercise the guard directly and through the CLI/in-process entry point.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from briefing.frontmatter_io import write

SCRIPTS_DIR = Path(__file__).parent.parent.parent  # .../scripts/
FEEDBACK_PKG = Path(__file__).parent.parent        # .../scripts/feedback/

sys.path.insert(0, str(SCRIPTS_DIR))
import feedback.feedback_archive as archive_mod  # noqa: E402
from feedback.feedback_archive import _archive_row_is_reconstructable  # noqa: E402


def run_archive(root: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(FEEDBACK_PKG / "feedback_archive.py")]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        env={
            "PYTHONPATH": str(SCRIPTS_DIR),
            "CONCLAVE_AI_ROOT": str(root),
            "PATH": "/usr/bin:/bin",
        },
    )


def _write_review(root: Path, date: str, filename: str, meta: dict, body: str = "") -> Path:
    out_dir = root / "ops" / "feedback" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    write(path, meta, body)
    return path


def _valid_item(item_id: str = "it-1", status: str = "resolved", observation: str = "broke") -> dict:
    return {
        "id": item_id,
        "category": "script-defect",
        "layer": "skill",
        "location": {"file": "a.sh", "line": 4},
        "observation": observation,
        "suggested_fix": "add null guard",
        "severity": "medium",
        "frequency": "first-time",
        "evidence": "tool_call:abc123",
        "status": status,
    }


def _valid_review_meta(feedback_id: str, items: list) -> dict:
    return {
        "feedback_id": feedback_id,
        "agent": "atlas",
        "agent_type": "executor",
        "session_ref": "test-session",
        "skill_version": "sha256:aabbcc",
        "created": "2026-05-22T10:00:00Z",
        "updated_at": "2026-05-22T10:00:00Z",
        "_draft": False,
        "summary": "test review",
        "items": items,
        "below_threshold_count": 0,
    }


# --- direct unit tests of the predicate ---

def test_predicate_rejects_missing_body_key():
    row = {"items": [{"observation": "x"}]}
    assert "body" not in row
    assert _archive_row_is_reconstructable(row) is False


def test_predicate_accepts_empty_body_string():
    row = {"items": [{"observation": "x"}], "body": ""}
    assert _archive_row_is_reconstructable(row) is True


def test_predicate_rejects_empty_items():
    row = {"items": [], "body": "notes"}
    assert _archive_row_is_reconstructable(row) is False


def test_predicate_rejects_item_with_empty_observation():
    row = {"items": [{"observation": "x"}, {"observation": ""}], "body": "notes"}
    assert _archive_row_is_reconstructable(row) is False


# --- CLI-level tests ---

def test_archives_and_unlinks_a_complete_review(tmp_path):
    """The normal case: a fully-closed review with two observed items is unlinked, and the
    JSONL row round-trips both observations and the body."""
    items = [
        _valid_item("it-1", "resolved", "first defect body"),
        _valid_item("it-2", "rejected", "second defect body"),
    ]
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-complete.md",
        _valid_review_meta("fb-complete-aaaaaa", items),
        body="Notes prose.",
    )

    result = run_archive(tmp_path)
    assert result.returncode == 0, result.stderr

    assert not review_path.exists(), "a reconstructable row must still unlink the markdown"

    archive_file = tmp_path / "ops" / "feedback" / "_archive" / "2026-05.jsonl"
    row = json.loads(archive_file.read_text().splitlines()[0])
    observations = [it["observation"] for it in row["items"]]
    assert "first defect body" in observations
    assert "second defect body" in observations
    assert row["body"] == "Notes prose."


def _archive_rows(tmp_path: Path, month: str = "2026-05") -> list[dict]:
    archive_file = tmp_path / "ops" / "feedback" / "_archive" / f"{month}.jsonl"
    if not archive_file.exists():
        return []
    return [json.loads(ln) for ln in archive_file.read_text().splitlines() if ln.strip()]


def test_refuses_to_unlink_when_row_has_no_items(tmp_path, monkeypatch):
    """A review closes with all items resolved, but the row-builder is forced to emit an
    empty `items` list (simulating the exact mutation the acceptance check performs) — the
    guard must refuse, leaving the markdown in place, reporting a non-zero result, and
    writing NOTHING to the JSONL (R4: the guard now runs before the append).
    """
    items = [_valid_item("it-1", "resolved", "will not survive")]
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-noitems.md",
        _valid_review_meta("fb-noitems-bbbbbb", items),
        body="Notes.",
    )
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))

    real_predicate = archive_mod._archive_row_is_reconstructable

    def _blanked(row):
        if row.get("feedback_id") == "fb-noitems-bbbbbb":
            row = {**row, "items": []}
        return real_predicate(row)

    monkeypatch.setattr(archive_mod, "_archive_row_is_reconstructable", _blanked)

    returncode = archive_mod.main([])

    assert review_path.exists(), "markdown must survive when the row cannot reconstruct it"
    assert returncode != 0, "refusal must be reported as a non-zero exit"
    assert not any(r.get("feedback_id") == "fb-noitems-bbbbbb" for r in _archive_rows(tmp_path)), \
        "a refused row must never reach the JSONL"


def test_refuses_to_unlink_when_an_item_body_is_empty(tmp_path):
    """One item carries an empty observation; the guard must refuse the unlink and write
    nothing to the JSONL (R4: checked before the append, not after)."""
    items = [
        _valid_item("it-1", "resolved", "fine"),
        _valid_item("it-2", "resolved", ""),
    ]
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-emptyobs.md",
        _valid_review_meta("fb-emptyobs-cccccc", items),
        body="Notes.",
    )

    result = run_archive(tmp_path)

    assert review_path.exists(), "markdown must survive when an item body is empty"
    assert result.returncode != 0
    assert "atlas-emptyobs.md" in result.stderr, result.stderr
    assert not any(r.get("feedback_id") == "fb-emptyobs-cccccc" for r in _archive_rows(tmp_path)), \
        "a refused row must never reach the JSONL"


def test_retry_succeeds_after_the_review_is_repaired(tmp_path):
    """R4's whole point: a refused review is not permanently stuck.

    Run 1: the review has an item with no observation — refused, no ledger row, markdown
    survives. The review is then repaired in place (as an operator would, editing the
    markdown itself — never the ledger, since the guard left no ledger row to edit). Run 2:
    the SAME feedback_id now archives and unlinks cleanly, because there was never a stale
    "already archived" row for `_load_archived_ids` to trip over.
    """
    items = [
        _valid_item("it-1", "resolved", "fine"),
        _valid_item("it-2", "resolved", ""),
    ]
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-repair.md",
        _valid_review_meta("fb-repair-dddddd", items),
        body="Notes.",
    )

    result1 = run_archive(tmp_path)
    assert result1.returncode != 0, "first run must refuse the incomplete review"
    assert review_path.exists()
    assert not any(r.get("feedback_id") == "fb-repair-dddddd" for r in _archive_rows(tmp_path))

    # Repair: give the empty item a real observation.
    repaired_items = [
        _valid_item("it-1", "resolved", "fine"),
        _valid_item("it-2", "resolved", "now filled in"),
    ]
    write(review_path, _valid_review_meta("fb-repair-dddddd", repaired_items), "Notes.")

    result2 = run_archive(tmp_path)
    assert result2.returncode == 0, result2.stderr
    assert not review_path.exists(), "the repaired review must archive and unlink on retry"

    rows = [r for r in _archive_rows(tmp_path) if r.get("feedback_id") == "fb-repair-dddddd"]
    assert len(rows) == 1
    observations = [it["observation"] for it in rows[0]["items"]]
    assert "now filled in" in observations
