"""test_index.py — TDD tests for feedback_index.py (T5)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from briefing.frontmatter_io import write

SCRIPTS_DIR = Path(__file__).parent.parent.parent  # .../scripts/
FEEDBACK_PKG = Path(__file__).parent.parent        # .../scripts/feedback/


def run_index(root: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(FEEDBACK_PKG / "feedback_index.py"),
    ]
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


def _valid_item(item_id: str = "it-1") -> dict:
    return {
        "id": item_id,
        "category": "script-defect",
        "layer": "skill",
        "location": {"file": "a.sh", "line": 4},
        "observation": "exits with 1 unexpectedly",
        "suggested_fix": "add null guard",
        "severity": "medium",
        "frequency": "first-time",
        "evidence": "tool_call:abc123",
    }


def _valid_review_meta(agent: str = "atlas", item_id: str = "it-1") -> dict:
    return {
        "feedback_id": "fb-111-aaaaaa",
        "agent": agent,
        "agent_type": "executor",
        "session_ref": "test-session",
        "skill_version": "sha256:aabbcc",
        "created": "2026-05-22T10:00:00Z",
        "updated_at": "2026-05-22T10:00:00Z",
        "_draft": False,
        "summary": "test review",
        "items": [_valid_item(item_id)],
        "below_threshold_count": 0,
    }


# --- Tests ---


def test_index_propagates_verify_block(tmp_path):
    """A review item's verify: predicate surfaces in its index row (093 P1 T1)."""
    meta = _valid_review_meta()
    meta["items"][0]["status"] = "accepted"
    meta["items"][0]["verify"] = {"kind": "grep-absent", "file": "a.sh", "pattern": "BUG"}
    _write_review(tmp_path, "2026-07-10", "atlas-verify.md", meta)
    run_index(tmp_path)
    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    rows = [json.loads(line) for line in index.read_text().splitlines() if line.strip()]
    row = next(r for r in rows if r["item_id"] == "it-1")
    # `root` is dumped from the model default, so a predicate written before #170 gains
    # an explicit "project" in its index row — the tree it was already resolving against.
    assert row["verify"] == {
        "kind": "grep-absent", "root": "project",
        "file": "a.sh", "path": None, "pattern": "BUG",
    }

def test_index_creates_jsonl(tmp_path):
    """A valid review produces one JSONL row in the index."""
    _write_review(tmp_path, "2026-05-22", "atlas-test.md", _valid_review_meta())
    result = run_index(tmp_path)
    assert result.returncode == 0, result.stderr

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    assert index.exists(), "index.jsonl not created"

    rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["item_id"] == "it-1"


def test_index_draft_skipped(tmp_path):
    """_draft: true reviews are skipped silently (no rows, exit 0)."""
    meta = _valid_review_meta()
    meta["_draft"] = True
    _write_review(tmp_path, "2026-05-22", "atlas-draft.md", meta)

    result = run_index(tmp_path)
    assert result.returncode == 0, result.stderr

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    if index.exists():
        rows = [ln for ln in index.read_text().splitlines() if ln.strip()]
        assert rows == [], f"draft rows should not appear in index: {rows}"


def test_index_rejects_missing_evidence(tmp_path):
    """Item missing evidence (and not migrated) is rejected; exit non-zero."""
    item = _valid_item()
    del item["evidence"]  # no evidence, not migrated → reject
    meta = _valid_review_meta()
    meta["items"] = [item]
    _write_review(tmp_path, "2026-05-22", "atlas-bad.md", meta)

    result = run_index(tmp_path)
    assert result.returncode != 0, "should exit non-zero on rejected item"
    assert "evidence" in result.stderr.lower() or "reject" in result.stderr.lower(), result.stderr


def test_index_migrated_item_exempt_from_evidence(tmp_path):
    """migrated: true items are accepted even without evidence."""
    item = _valid_item()
    del item["evidence"]
    item["migrated"] = True
    item["legacy_source"] = "journal.jsonl#fb-x"
    meta = _valid_review_meta()
    meta["items"] = [item]
    _write_review(tmp_path, "2026-05-22", "atlas-migrated.md", meta)

    result = run_index(tmp_path)
    assert result.returncode == 0, result.stderr

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["migrated"] is True


def test_index_fingerprint_computed(tmp_path):
    """Index rows have a non-null fingerprint computed from location+category."""
    _write_review(tmp_path, "2026-05-22", "atlas-fp.md", _valid_review_meta())
    run_index(tmp_path)

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    row = json.loads(index.read_text().splitlines()[0])
    assert row.get("fingerprint"), "fingerprint must be set in index row"


def test_index_check_mode(tmp_path):
    """--check prints reviews=N pending_triage=N without writing index."""
    _write_review(tmp_path, "2026-05-22", "atlas-check.md", _valid_review_meta())
    result = run_index(tmp_path, extra_args=["--check"])
    assert result.returncode == 0, result.stderr
    assert "reviews=" in result.stdout
    assert "pending_triage=" in result.stdout

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    assert not index.exists(), "--check must not write index"


def test_index_incremental_no_duplicate(tmp_path):
    """Running index twice on unchanged review produces exactly one row."""
    _write_review(tmp_path, "2026-05-22", "atlas-inc.md", _valid_review_meta())

    run_index(tmp_path)
    run_index(tmp_path)  # second run — same updated_at

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1, f"incremental skip failed: got {len(rows)} rows"


def test_index_also_indexes_migrated_dir(tmp_path):
    """Reviews in _migrated/ are indexed alongside dated dirs."""
    migrated_dir = tmp_path / "ops" / "feedback" / "_migrated"
    migrated_dir.mkdir(parents=True, exist_ok=True)
    meta = _valid_review_meta()
    meta["items"][0]["migrated"] = True
    meta["items"][0]["legacy_source"] = "journal.jsonl#fb-y"
    del meta["items"][0]["evidence"]
    path = migrated_dir / "atlas-legacy.md"
    write(path, meta, "")

    result = run_index(tmp_path)
    assert result.returncode == 0, result.stderr

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1


def test_index_draft_false_invalid_exits_nonzero_with_dropped_line(tmp_path):
    """A _draft:false file that fails schema validation causes non-zero exit and
    prints a DROPPED summary line to stderr. The file must NOT appear in the index.
    Regression for spec 086 item-3: author-complete reviews were silently dropped."""
    # Create an invalid _draft:false review (missing evidence, not migrated)
    item = _valid_item()
    del item["evidence"]   # schema requires evidence when not migrated
    meta = _valid_review_meta()
    meta["items"] = [item]
    meta["_draft"] = False  # author-complete
    _write_review(tmp_path, "2026-05-22", "atlas-invalid-complete.md", meta)

    result = run_index(tmp_path)

    # Must exit non-zero
    assert result.returncode != 0, (
        "feedback_index.py must exit non-zero when a _draft:false file fails schema validation"
    )
    # Must print DROPPED summary to stderr
    assert "DROPPED" in result.stderr, (
        f"Expected 'DROPPED' in stderr; got: {result.stderr!r}"
    )
    assert "author-complete" in result.stderr, (
        f"Expected 'author-complete' in stderr; got: {result.stderr!r}"
    )
    # The invalid file must not appear in the index
    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    if index.exists():
        rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
        indexed_ids = [r.get("feedback_id") for r in rows]
        assert meta["feedback_id"] not in indexed_ids, (
            "Invalid _draft:false review must not appear in index"
        )


def test_index_rebuild_reflects_status_change_on_updated_at_tie(tmp_path):
    """Regression for issue #8: a batch of feedback_triage.py --set calls can leave
    multiple items sharing the same final review updated_at. When the review file's
    updated_at ties the already-indexed value exactly, a rebuild must still pick up
    a status change made on disk instead of skipping the item as "already indexed"."""
    path = _write_review(tmp_path, "2026-05-22", "atlas-tie.md", _valid_review_meta())
    run_index(tmp_path)

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    assert rows[0]["status"] == "open"

    # Simulate feedback_triage.py --set: item status changes on disk, but
    # updated_at stays the same second (ties the already-indexed timestamp).
    meta = _valid_review_meta()
    meta["items"][0]["status"] = "accepted"
    write(path, meta, "")

    run_index(tmp_path)

    rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["status"] == "accepted", (
        "rebuild must not skip a re-read on an updated_at tie: stale status survived"
    )


def test_index_draft_true_invalid_does_not_exit_nonzero(tmp_path):
    """A _draft:true file that would fail schema validation is skipped silently (exit 0).
    Only _draft:false failures are loud — drafts are still being authored."""
    item = _valid_item()
    del item["evidence"]   # would fail schema, but _draft:true so silently skipped
    meta = _valid_review_meta()
    meta["items"] = [item]
    meta["_draft"] = True  # still being authored

    _write_review(tmp_path, "2026-05-22", "atlas-draft-invalid.md", meta)

    result = run_index(tmp_path)

    # Draft files are silently skipped regardless of validity
    assert result.returncode == 0, (
        f"_draft:true files must be skipped silently; got exit {result.returncode}, "
        f"stderr: {result.stderr!r}"
    )
    assert "DROPPED" not in result.stderr, (
        "DROPPED must not appear for _draft:true files"
    )


# --- #9: --rebuild writes a clean index (drops stale rows) ---

def test_rebuild_drops_stale_rows_from_deleted_review(tmp_path):
    """--rebuild writes a clean index from the live review files, dropping rows
    whose source review was deleted/archived. The incremental+merge default keeps
    them (the merge is load-bearing for the skip optimisation), so triage must
    rebuild to purge stale rows (#9)."""
    idx = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    review = _write_review(tmp_path, "2026-05-22", "a.md", _valid_review_meta())

    run_index(tmp_path)  # incremental build
    assert "fb-111-aaaaaa" in idx.read_text(), "row missing after initial build"

    review.unlink()  # simulate archive/removal of the source review

    run_index(tmp_path)  # incremental default preserves the now-stale row
    assert "fb-111-aaaaaa" in idx.read_text(), \
        "sanity: incremental+merge default keeps the stale row"

    res = run_index(tmp_path, ["--rebuild"])
    assert res.returncode == 0, res.stderr
    assert "fb-111-aaaaaa" not in idx.read_text(), \
        "--rebuild must drop the row whose source review is gone"


def test_rebuild_keeps_live_rows(tmp_path):
    """--rebuild re-processes every live review (ignores incremental skip), so
    unchanged rows are still present in the clean index."""
    idx = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    _write_review(tmp_path, "2026-05-22", "a.md", _valid_review_meta())

    res = run_index(tmp_path, ["--rebuild"])
    assert res.returncode == 0, res.stderr
    assert "fb-111-aaaaaa" in idx.read_text(), "--rebuild dropped a live row"
