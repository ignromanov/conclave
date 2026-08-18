"""test_archive.py — TDD tests for feedback_archive.py (T7)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from briefing.frontmatter_io import read as fm_read
from briefing.frontmatter_io import write

SCRIPTS_DIR = Path(__file__).parent.parent.parent  # .../scripts/
FEEDBACK_PKG = Path(__file__).parent.parent        # .../scripts/feedback/


def run_archive(root: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(FEEDBACK_PKG / "feedback_archive.py"),
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


def _valid_item(item_id: str = "it-1", status: str = "open") -> dict:
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
        "status": status,
    }


def _valid_review_meta(feedback_id: str = "fb-111-aaaaaa", items: list | None = None) -> dict:
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
        "items": items if items is not None else [_valid_item()],
        "below_threshold_count": 0,
    }


# --- Tests ---

def test_archive_moves_fully_resolved_review(tmp_path):
    """A review whose items are all resolved is moved to _archive/YYYY-MM.jsonl."""
    resolved_items = [_valid_item("it-1", "resolved"), _valid_item("it-2", "rejected")]
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-done.md",
        _valid_review_meta(feedback_id="fb-111-aaaaaa", items=resolved_items)
    )

    result = run_archive(tmp_path)
    assert result.returncode == 0, result.stderr

    # Source file removed
    assert not review_path.exists(), "source markdown must be removed after archive"

    # Archive line present
    archive_file = tmp_path / "ops" / "feedback" / "_archive" / "2026-05.jsonl"
    assert archive_file.exists(), "_archive/2026-05.jsonl not created"
    lines = [json.loads(ln) for ln in archive_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0]["feedback_id"] == "fb-111-aaaaaa"


def test_archive_leaves_open_review_untouched(tmp_path):
    """A review with at least one open item is never archived AS A REVIEW.

    Its closed items are archived individually (see the partial-archive test below), so the
    guard here is on review-kind rows, not on the bare presence of the feedback_id.
    """
    mixed_items = [_valid_item("it-1", "resolved"), _valid_item("it-2", "open")]
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-open.md",
        _valid_review_meta(feedback_id="fb-222-bbbbbb", items=mixed_items)
    )

    result = run_archive(tmp_path)
    assert result.returncode == 0, result.stderr

    # Source file still present
    assert review_path.exists(), "open review must not be archived"

    # No REVIEW-kind archive line for this id
    archive_file = tmp_path / "ops" / "feedback" / "_archive" / "2026-05.jsonl"
    if archive_file.exists():
        lines = [json.loads(ln) for ln in archive_file.read_text().splitlines() if ln.strip()]
        ids = [ln["feedback_id"] for ln in lines if ln.get("kind") != "item"]
        assert "fb-222-bbbbbb" not in ids


def test_archive_closes_items_of_a_partially_closed_review(tmp_path):
    """The archive unit is the ITEM: a closed item is archived even while a sibling is open.

    Without this, a single lingering item pins its whole review forever — measured on the
    live instance as 60 live reviews, 0 of them fully closed, and an archiver that had
    never once fired.
    """
    mixed = [_valid_item("it-1", "resolved"), _valid_item("it-2", "open")]
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-partial.md",
        _valid_review_meta(feedback_id="fb-444-dddddd", items=mixed)
    )

    result = run_archive(tmp_path)
    assert result.returncode == 0, result.stderr

    # The review file survives — nothing is cut out of the source of truth
    assert review_path.exists()
    text = review_path.read_text()
    assert "it-1" in text and "it-2" in text, "no item may be removed from the review"

    archive_file = tmp_path / "ops" / "feedback" / "_archive" / "2026-05.jsonl"
    rows = [json.loads(ln) for ln in archive_file.read_text().splitlines() if ln.strip()]
    item_rows = [r for r in rows if r.get("kind") == "item"
                 and r.get("feedback_id") == "fb-444-dddddd"]
    assert len(item_rows) == 1, "exactly the closed item is archived"
    assert item_rows[0]["item_id"] == "it-1"
    assert item_rows[0]["item"]["id"] == "it-1", "the row carries the item verbatim"

    # The closed item is stamped; the open one is not
    meta, _ = fm_read(review_path)
    by_id = {i["id"]: i for i in meta["items"]}
    assert by_id["it-1"].get("archived_at"), "closed item must be stamped archived_at"
    assert not by_id["it-2"].get("archived_at"), "open item must not be stamped"


def test_archive_stamps_an_item_the_ledger_already_holds(tmp_path):
    """Recovery: ledger row written, review stamp lost — the retry stamps, never duplicates.

    The append and the stamp are two writes to two files. If only the first lands, the key
    guard would block the retry and the item would sit in the index forever, closed but
    unstamped. Stamping is driven by status, appending by the ledger.
    """
    mixed = [_valid_item("it-1", "resolved"), _valid_item("it-2", "open")]
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-halfwritten.md",
        _valid_review_meta(feedback_id="fb-666-ffffff", items=mixed)
    )

    # Simulate the crashed run: ledger row present, review never stamped.
    arch_dir = tmp_path / "ops" / "feedback" / "_archive"
    arch_dir.mkdir(parents=True, exist_ok=True)
    (arch_dir / "2026-05.jsonl").write_text(json.dumps({
        "kind": "item", "feedback_id": "fb-666-ffffff", "item_id": "it-1",
        "archived_at": "2026-05-22T00:00:00+00:00", "item": {"id": "it-1"},
    }) + "\n")

    assert run_archive(tmp_path).returncode == 0

    rows = [json.loads(ln) for ln in (arch_dir / "2026-05.jsonl").read_text().splitlines()
            if ln.strip()]
    mine = [r for r in rows if r.get("feedback_id") == "fb-666-ffffff"]
    assert len(mine) == 1, f"must not duplicate the ledger row, got {len(mine)}"

    meta, _ = fm_read(review_path)
    by_id = {i["id"]: i for i in meta["items"]}
    assert by_id["it-1"].get("archived_at"), "the unstamped ledgered item must get stamped"


def test_archive_does_not_re_archive_an_already_archived_item(tmp_path):
    """Running twice appends the item row once — the (feedback_id, item_id) guard holds."""
    mixed = [_valid_item("it-1", "resolved"), _valid_item("it-2", "open")]
    _write_review(
        tmp_path, "2026-05-22", "atlas-twice.md",
        _valid_review_meta(feedback_id="fb-555-eeeeee", items=mixed)
    )

    assert run_archive(tmp_path).returncode == 0
    assert run_archive(tmp_path).returncode == 0

    archive_file = tmp_path / "ops" / "feedback" / "_archive" / "2026-05.jsonl"
    rows = [json.loads(ln) for ln in archive_file.read_text().splitlines() if ln.strip()]
    mine = [r for r in rows if r.get("feedback_id") == "fb-555-eeeeee"]
    assert len(mine) == 1, f"expected one row after two runs, got {len(mine)}"


def test_archive_appends_to_hot_md(tmp_path):
    """Archiving a resolved review appends a finding line to agent-memory/hot.md."""
    resolved_items = [_valid_item("it-1", "resolved")]
    _write_review(
        tmp_path, "2026-05-22", "atlas-hot.md",
        _valid_review_meta(feedback_id="fb-333-cccccc", items=resolved_items)
    )

    # Create agent-memory dir (needed for hot.md path)
    (tmp_path / "agent-memory").mkdir(parents=True, exist_ok=True)

    result = run_archive(tmp_path)
    assert result.returncode == 0, result.stderr

    hot_md = tmp_path / "agent-memory" / "hot.md"
    assert hot_md.exists(), "hot.md must be created/appended"
    content = hot_md.read_text()
    assert "fb-333-cccccc" in content, "archived feedback_id must appear in hot.md"


def test_archive_refuses_re_archive(tmp_path):
    """Re-archiving an already-archived id exits non-zero with an error."""
    resolved_items = [_valid_item("it-1", "resolved")]
    _write_review(
        tmp_path, "2026-05-22", "atlas-dup.md",
        _valid_review_meta(feedback_id="fb-444-dddddd", items=resolved_items)
    )

    # First archive — should succeed
    result1 = run_archive(tmp_path)
    assert result1.returncode == 0, result1.stderr

    # Recreate the review file to simulate re-run attempt
    _write_review(
        tmp_path, "2026-05-22", "atlas-dup2.md",
        _valid_review_meta(feedback_id="fb-444-dddddd", items=resolved_items)
    )

    # Second archive — should refuse
    result2 = run_archive(tmp_path)
    assert result2.returncode != 0, "re-archiving same id must fail"
    assert "already" in result2.stderr.lower() or "exist" in result2.stderr.lower() or \
           "duplicate" in result2.stderr.lower() or "re-archive" in result2.stderr.lower(), \
           result2.stderr


def test_archive_note_appears_in_hot_md(tmp_path):
    """--note text is appended to the hot.md line."""
    resolved_items = [_valid_item("it-1", "resolved")]
    _write_review(
        tmp_path, "2026-05-22", "atlas-note.md",
        _valid_review_meta(feedback_id="fb-note-777777", items=resolved_items)
    )
    (tmp_path / "agent-memory").mkdir(parents=True, exist_ok=True)

    result = run_archive(tmp_path, extra_args=["--note", "spec-086 cleanup"])
    assert result.returncode == 0, result.stderr

    hot_md = tmp_path / "agent-memory" / "hot.md"
    content = hot_md.read_text()
    assert "spec-086 cleanup" in content


def test_archive_only_resolved_in_mixed_batch(tmp_path):
    """With one resolved and one open review, only the resolved one is archived."""
    resolved_items = [_valid_item("it-1", "resolved")]
    open_items = [_valid_item("it-1", "open")]

    resolved_path = _write_review(
        tmp_path, "2026-05-22", "atlas-res.md",
        _valid_review_meta(feedback_id="fb-555-eeeee", items=resolved_items)
    )
    open_path = _write_review(
        tmp_path, "2026-05-22", "atlas-open2.md",
        _valid_review_meta(feedback_id="fb-666-ffffff", items=open_items)
    )

    result = run_archive(tmp_path)
    assert result.returncode == 0, result.stderr

    assert not resolved_path.exists(), "resolved review must be archived (removed)"
    assert open_path.exists(), "open review must remain"

    archive_file = tmp_path / "ops" / "feedback" / "_archive" / "2026-05.jsonl"
    lines = [json.loads(ln) for ln in archive_file.read_text().splitlines() if ln.strip()]
    ids = {ln["feedback_id"] for ln in lines}
    assert "fb-555-eeeee" in ids
    assert "fb-666-ffffff" not in ids


import re as _re


def _valid_item_with_skill(item_id: str = "it-1", status: str = "resolved",
                            skill: str = "team.done") -> dict:
    return {
        "id": item_id,
        "category": "script-defect",
        "layer": "skill",
        "location": {"skill": skill},
        "observation": "exits with 1 unexpectedly",
        "suggested_fix": "add null guard",
        "severity": "medium",
        "frequency": "first-time",
        "evidence": "tool_call:abc123",
        "status": status,
    }


def test_archive_row_preserves_every_item_and_the_body(tmp_path):
    """Principle VI: `unlink()` may only collapse a projection, not destroy the record.

    The archive row is the record; hot.md is a cache. Before this test, the row carried
    only a summary + item_count, hot.md deduped items on (feedback_id, skill_slug) and
    truncated the survivor to 120 chars — so archiving a two-item review destroyed the
    second item (here: the `critical` one) and the body prose outright, exit 0, silently.
    """
    long_obs = "FIRST - " + "x" * 200
    items = [
        {**_valid_item_with_skill("it-1", "resolved", "team.done"), "observation": long_obs},
        {
            **_valid_item_with_skill("it-2", "resolved", "team.done"),
            "observation": "SECOND - a different defect, same skill slug",
            "severity": "critical",
        },
    ]
    _write_review(
        tmp_path, "2026-05-22", "atlas-lossless.md",
        _valid_review_meta(feedback_id="fb-loss-aabbcc", items=items),
        body="Body prose that exists nowhere else.",
    )

    result = run_archive(tmp_path)
    assert result.returncode == 0, result.stderr

    archive_file = tmp_path / "ops" / "feedback" / "_archive" / "2026-05.jsonl"
    row = json.loads(archive_file.read_text().splitlines()[0])

    # Both items survive, in full — not a count, not a truncation.
    assert len(row["items"]) == 2, "archive row must carry every item, not item_count alone"
    observations = [it["observation"] for it in row["items"]]
    assert long_obs in observations, "item observation must survive untruncated"
    assert any("SECOND" in o for o in observations), (
        "the second item on the same skill slug must survive — hot.md's dedup is a cache "
        "concern and must not reach the record"
    )
    assert any(it["severity"] == "critical" for it in row["items"])

    # The markdown body is content too.
    assert "Body prose that exists nowhere else." in row["body"]


def test_hot_md_append_uses_structured_format_with_skill_slug(tmp_path):
    """#49b: the finding is written via the section-aware writer, so the structured
    marker [RESOLVED fb-<id>] <skill_slug>: <finding> (was <severity>) is embedded in
    a '- [<ts>] <agent>: …' bullet under ## Recent decisions (not raw at line start)."""
    items = [_valid_item_with_skill("it-1", "resolved", "team.done")]
    _write_review(
        tmp_path, "2026-05-22", "atlas-struct.md",
        _valid_review_meta(feedback_id="fb-struct-aabbcc", items=items)
    )
    (tmp_path / "agent-memory").mkdir(parents=True, exist_ok=True)

    result = run_archive(tmp_path)
    assert result.returncode == 0, result.stderr

    hot_md = tmp_path / "agent-memory" / "hot.md"
    assert hot_md.exists(), "hot.md must be created"
    content = hot_md.read_text()

    # Well-formed skeleton (no more raw dump below "## Last updated").
    assert "## Recent decisions" in content
    # Structured marker embedded in a section-aware bullet.
    pattern = _re.compile(
        r"^- \[[^\]]+\] [\w-]+: \[RESOLVED fb-[a-z0-9-]+\] team\.[a-z-]+: "
        r".+ \(was (low|medium|high|critical)\)$",
        _re.MULTILINE,
    )
    assert pattern.search(content), (
        f"hot.md line does not match section-aware structured format.\nContent:\n{content}"
    )


def test_archive_reconciles_the_index_it_just_invalidated(tmp_path):
    """Archiving must leave the cache agreeing with the tree it just changed.

    An archived item is stamped out of the working set and an archived review's file is
    gone, but the index keeps their rows until a rebuild — so without this the closed work
    keeps costing every index consumer exactly as much as it did before.
    """
    mixed = [_valid_item("it-1", "resolved"), _valid_item("it-2", "open")]
    _write_review(
        tmp_path, "2026-05-22", "atlas-reconcile.md",
        _valid_review_meta(feedback_id="fb-888-aaaaaa", items=mixed)
    )

    assert run_archive(tmp_path).returncode == 0

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    assert index.exists(), "archive must leave an index behind"
    rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    ids = {(r["feedback_id"], r["item_id"]) for r in rows}
    assert ("fb-888-aaaaaa", "it-1") not in ids, "archived item must leave the working set"
    assert ("fb-888-aaaaaa", "it-2") in ids, "the open sibling must stay in the working set"
