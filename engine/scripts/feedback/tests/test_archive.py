"""test_archive.py — TDD tests for feedback_archive.py (T7)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
    """A review with at least one open item is not archived."""
    mixed_items = [_valid_item("it-1", "resolved"), _valid_item("it-2", "open")]
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-open.md",
        _valid_review_meta(feedback_id="fb-222-bbbbbb", items=mixed_items)
    )

    result = run_archive(tmp_path)
    assert result.returncode == 0, result.stderr

    # Source file still present
    assert review_path.exists(), "open review must not be archived"

    # No archive line for this id
    archive_file = tmp_path / "ops" / "feedback" / "_archive" / "2026-05.jsonl"
    if archive_file.exists():
        lines = [json.loads(ln) for ln in archive_file.read_text().splitlines() if ln.strip()]
        ids = [ln["feedback_id"] for ln in lines]
        assert "fb-222-bbbbbb" not in ids


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
    """Principle VI (never silent-delete): `unlink()` may only collapse a projection.

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
