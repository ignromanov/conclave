"""test_item_touched_at.py — TDD tests for item-level touched_at (#218).

Closing one item in a review currently restamps every sibling row's `updated_at`
purely from being in the same rewritten file. `touched_at` is a per-item field,
set only by a write path that modified that exact item, never backfilled — an
untouched item's `touched_at` is unknown, not the review's timestamp.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from briefing.frontmatter_io import write

SCRIPTS_DIR = Path(__file__).parent.parent.parent  # .../scripts/
FEEDBACK_PKG = Path(__file__).parent.parent        # .../scripts/feedback/


def _env(root: Path) -> dict:
    return {
        "PYTHONPATH": str(SCRIPTS_DIR),
        "CONCLAVE_AI_ROOT": str(root),
        "PATH": "/usr/bin:/bin",
    }


def run_index(root: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(FEEDBACK_PKG / "feedback_index.py")]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True, env=_env(root))


def run_triage(root: Path, extra_args: list[str]) -> subprocess.CompletedProcess:
    args = [sys.executable, str(FEEDBACK_PKG / "feedback_triage.py"), *extra_args]
    return subprocess.run(args, capture_output=True, text=True, env=_env(root))


def run_verify(root: Path, extra_args: list[str]) -> subprocess.CompletedProcess:
    args = [sys.executable, str(FEEDBACK_PKG / "feedback_verify.py"), *extra_args]
    return subprocess.run(args, capture_output=True, text=True, env=_env(root))


def _write_review(root: Path, date: str, filename: str, meta: dict, body: str = "") -> Path:
    out_dir = root / "ops" / "feedback" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    write(path, meta, body)
    return path


def _valid_item(item_id: str, file: str, status: str = "open") -> dict:
    return {
        "id": item_id,
        "category": "script-defect",
        "layer": "skill",
        "location": {"file": file, "line": 4},
        "observation": "exits with 1 unexpectedly",
        "suggested_fix": "add null guard",
        "severity": "medium",
        "frequency": "first-time",
        "evidence": "tool_call:abc123",
        "status": status,
    }


def _three_item_review(feedback_id: str) -> dict:
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
        "items": [
            _valid_item("it-1", "a.sh"),
            _valid_item("it-2", "b.sh"),
            _valid_item("it-3", "c.sh"),
        ],
        "below_threshold_count": 0,
    }


def _rows_by_item(root: Path) -> dict[str, dict]:
    index = root / "ops" / "feedback" / "_index" / "index.jsonl"
    rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    return {r["item_id"]: r for r in rows}


# --- Tests ---


def test_closing_one_item_does_not_move_a_siblings_touched_at(tmp_path):
    """Setting one item's status stamps touched_at on THAT item only; the two
    untouched siblings keep touched_at == "" (never individually touched).
    updated_at, the review-level field, DOES move for all three — that is the
    documented, deliberately unchanged behaviour this test pins."""
    _write_review(tmp_path, "2026-05-22", "atlas-siblings.md",
                  _three_item_review("fb-touch-aaaaaa"))

    result = run_index(tmp_path)
    assert result.returncode == 0, result.stderr
    before = _rows_by_item(tmp_path)
    assert before["it-1"]["touched_at"] == ""
    assert before["it-2"]["touched_at"] == ""
    assert before["it-3"]["touched_at"] == ""
    updated_before = before["it-1"]["updated_at"]

    result = run_triage(tmp_path, ["--set", "fb-touch-aaaaaa", "it-1", "resolved"])
    assert result.returncode == 0, result.stderr

    result = run_index(tmp_path)
    assert result.returncode == 0, result.stderr
    after = _rows_by_item(tmp_path)

    # The modified item: touched_at is now stamped.
    assert after["it-1"]["touched_at"] != "", "modified item must gain a touched_at"

    # The untouched siblings: touched_at stays absent, never backfilled from the
    # review-level updated_at.
    assert after["it-2"]["touched_at"] == "", \
        f"sibling touched_at must stay unknown, got {after['it-2']['touched_at']!r}"
    assert after["it-3"]["touched_at"] == "", \
        f"sibling touched_at must stay unknown, got {after['it-3']['touched_at']!r}"

    # Documented review-level behaviour, pinned deliberately: updated_at DOES move
    # for every item in the rewritten file, siblings included.
    assert after["it-2"]["updated_at"] != updated_before
    assert after["it-3"]["updated_at"] != updated_before


def test_set_verify_stamps_touched_at_on_its_item_only(tmp_path):
    """--set-verify stamps touched_at on the one item it attaches a predicate to,
    using the same timestamp it writes to the review's updated_at."""
    data_root = tmp_path / ".conclave"
    (tmp_path / "foo.py").write_text("still has the BUG\n")
    meta = {
        "feedback_id": "fb-sv-aaaaaa", "agent": "sage-cto", "agent_type": "advisor",
        "session_ref": "s1", "skill_version": "sha256:aabbcc",
        "created": "2026-07-10T00:00:00Z", "updated_at": "2026-07-10T00:00:00Z",
        "_draft": False, "summary": "t", "below_threshold_count": 0,
        "items": [
            {"id": "i1", "category": "script-defect", "layer": "skill",
             "location": {"file": "foo.py"}, "observation": "o",
             "suggested_fix": "x", "severity": "high", "frequency": "occasional",
             "evidence": "tc:1", "status": "accepted"},
            {"id": "i2", "category": "script-defect", "layer": "skill",
             "location": {"file": "bar.py"}, "observation": "o",
             "suggested_fix": "x", "severity": "high", "frequency": "occasional",
             "evidence": "tc:1", "status": "accepted"},
        ],
    }
    review_path = _write_review(data_root, "2026-07-10", "sage-setverify.md", meta)

    result = run_verify(data_root, ["--set-verify", "fb-sv-aaaaaa", "i1", "grep-absent",
                                    "--file", "foo.py", "--pattern", "BUG"])
    assert result.returncode == 0, result.stderr

    from briefing.frontmatter_io import read_commented
    meta_after, _ = read_commented(review_path)
    item1 = next(i for i in meta_after["items"] if i["id"] == "i1")
    item2 = next(i for i in meta_after["items"] if i["id"] == "i2")

    assert item1.get("touched_at"), "the attached-to item must gain a touched_at"
    assert str(item1["touched_at"]) == str(meta_after["updated_at"]), \
        "touched_at must match the same timestamp written to updated_at"
    assert not item2.get("touched_at"), "the untouched sibling must not gain a touched_at"


def test_index_row_touched_at_is_empty_for_an_untouched_item(tmp_path):
    """An item that has never been through a write path indexes with
    touched_at == "" — absence, not a fallback to the review's updated_at."""
    _write_review(tmp_path, "2026-05-22", "atlas-untouched.md",
                  _three_item_review("fb-untouched-aaaaaa"))

    result = run_index(tmp_path)
    assert result.returncode == 0, result.stderr

    rows = _rows_by_item(tmp_path)
    assert rows["it-1"]["touched_at"] == ""
    assert rows["it-1"]["touched_at"] != rows["it-1"]["updated_at"]
