"""test_migrate.py — TDD tests for feedback_migrate.py (T8)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from briefing.frontmatter_io import read as fm_read

SCRIPTS_DIR = Path(__file__).parent.parent.parent  # .../scripts/
FEEDBACK_PKG = Path(__file__).parent.parent        # .../scripts/feedback/


def run_migrate(root: Path, channel_a: Path | None = None, channel_b_dir: Path | None = None,
                dry_run: bool = False) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(FEEDBACK_PKG / "feedback_migrate.py"),
    ]
    if channel_a:
        args += ["--channel-a", str(channel_a)]
    if channel_b_dir:
        args += ["--channel-b", str(channel_b_dir)]
    if dry_run:
        args += ["--dry-run"]
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


# --- Channel A fixture (2 rows) ---

CHANNEL_A_ROWS = [
    {
        "id": "fb-1777403985-3de6cc",
        "ts": "2026-04-28T19:19:45Z",
        "advisor": "quorum",
        "skill": "team.quorum",
        "scope": "docs",
        "severity": "medium",
        "type": "inconsistency",
        "location": ".claude/skills/team.quorum/SKILL.md:108",
        "message": "SKILL.md body has 7 update instructions that contradict spec 051 invariants.",
        "run_id": "session-2026-04-28-quorum",
    },
    {
        "id": "fb-1777403995-b07606",
        "ts": "2026-04-28T19:19:55Z",
        "advisor": "quorum",
        "skill": "team.quorum",
        "scope": "docs",
        "severity": "blocker",   # <-- maps to "critical"
        "type": "docs-gap",
        "location": ".claude/skills/team.quorum/SKILL.md:323",
        "message": "Broken relative path in docs.",
        "run_id": "session-2026-04-28-quorum",
    },
]

# --- Channel B fixture (1 file) ---

CHANNEL_B_FRONTMATTER = """\
---
emission_id: 2026-05-17-atlas-076-T15-vault-setup
emitted_at: 2026-05-17T06:20:00Z
emitter: exec.atlas-dev
skill_id: exec.atlas-dev
skill_version: sha256:a30fce6aba3c
session_ref: ops/specs/076-lifecycle-bash-extraction
dispatch_id: T15-vault-setup
_draft: false
status: ok
severity: low
would_use_again: true
improvisations:
  - "Vault root path in spec said agent-memory/ but E8 had not yet landed"
missing_context_anchors:
  - "exec.atlas-dev/SKILL.md: no docs-only task branch"
friction_note: "The spec pointed at agent-memory/ but ground truth had shifted."
suggested_fix: "Add a docs-only task variant to exec.atlas-dev SKILL.md."
---

## ASI

Some body content here.
"""


def _make_channel_a(tmp_path: Path) -> Path:
    journal = tmp_path / "journal.jsonl"
    with journal.open("w") as f:
        for row in CHANNEL_A_ROWS:
            f.write(json.dumps(row) + "\n")
    return journal


def _make_channel_b_dir(tmp_path: Path) -> Path:
    b_dir = tmp_path / "skill-feedback" / "2026-05-17"
    b_dir.mkdir(parents=True, exist_ok=True)
    (b_dir / "atlas-076-T15-vault-setup.md").write_text(CHANNEL_B_FRONTMATTER)
    return tmp_path / "skill-feedback"


# --- Tests ---

def test_migrate_produces_3_items(tmp_path):
    """2 channel-A rows + 1 channel-B file → 3 migrated items total."""
    journal = _make_channel_a(tmp_path)
    b_dir = _make_channel_b_dir(tmp_path)

    result = run_migrate(tmp_path, channel_a=journal, channel_b_dir=b_dir)
    assert result.returncode == 0, result.stderr

    migrated_dir = tmp_path / "ops" / "feedback" / "_migrated"
    assert migrated_dir.exists(), "_migrated dir not created"

    all_items = []
    for md in migrated_dir.glob("*.md"):
        meta, _ = fm_read(md)
        all_items.extend(meta.get("items", []))

    assert len(all_items) == 3, f"expected 3 items, got {len(all_items)}: {all_items}"


def test_migrate_all_items_migrated_true(tmp_path):
    """Every produced item has migrated: true."""
    journal = _make_channel_a(tmp_path)
    b_dir = _make_channel_b_dir(tmp_path)

    run_migrate(tmp_path, channel_a=journal, channel_b_dir=b_dir)

    migrated_dir = tmp_path / "ops" / "feedback" / "_migrated"
    for md in migrated_dir.glob("*.md"):
        meta, _ = fm_read(md)
        for item in meta.get("items", []):
            assert item.get("migrated") is True, f"item {item.get('id')} missing migrated=true"


def test_migrate_legacy_source_set(tmp_path):
    """Every produced item has legacy_source set."""
    journal = _make_channel_a(tmp_path)
    b_dir = _make_channel_b_dir(tmp_path)

    run_migrate(tmp_path, channel_a=journal, channel_b_dir=b_dir)

    migrated_dir = tmp_path / "ops" / "feedback" / "_migrated"
    for md in migrated_dir.glob("*.md"):
        meta, _ = fm_read(md)
        for item in meta.get("items", []):
            assert item.get("legacy_source"), f"item {item.get('id')} missing legacy_source"


def test_migrate_blocker_maps_to_critical(tmp_path):
    """Channel-A severity 'blocker' maps to 'critical'."""
    journal = _make_channel_a(tmp_path)

    run_migrate(tmp_path, channel_a=journal)

    migrated_dir = tmp_path / "ops" / "feedback" / "_migrated"
    severities = []
    for md in migrated_dir.glob("*.md"):
        meta, _ = fm_read(md)
        for item in meta.get("items", []):
            severities.append(item.get("severity"))

    assert "critical" in severities, f"blocker→critical mapping failed; got severities={severities}"


def test_migrate_evidence_absent_no_validation_error(tmp_path):
    """Migrated items without evidence must not cause a ValidationError (migrated flag exempts them)."""
    from pydantic import ValidationError

    from feedback.schema import FeedbackItem

    journal = _make_channel_a(tmp_path)
    run_migrate(tmp_path, channel_a=journal)

    migrated_dir = tmp_path / "ops" / "feedback" / "_migrated"
    for md in migrated_dir.glob("*.md"):
        meta, _ = fm_read(md)
        for item_dict in meta.get("items", []):
            # Must not raise
            try:
                FeedbackItem.model_validate(item_dict)
            except ValidationError as exc:
                pytest.fail(f"ValidationError on migrated item {item_dict.get('id')}: {exc}")


def test_migrate_prints_count_summary(tmp_path):
    """Output includes count of migrated items."""
    journal = _make_channel_a(tmp_path)
    b_dir = _make_channel_b_dir(tmp_path)

    result = run_migrate(tmp_path, channel_a=journal, channel_b_dir=b_dir)
    assert result.returncode == 0, result.stderr
    # Should print something like "migrated: 3 items" or "3 items migrated"
    combined = result.stdout + result.stderr
    assert any(c.isdigit() for c in combined), f"no count in output: {combined!r}"


# --- T-F': --dry-run tests ---

def test_dry_run_writes_no_files(tmp_path):
    """--dry-run must not create _migrated/ or write any .md files."""
    journal = _make_channel_a(tmp_path)
    b_dir = _make_channel_b_dir(tmp_path)

    result = run_migrate(tmp_path, channel_a=journal, channel_b_dir=b_dir, dry_run=True)
    assert result.returncode == 0, result.stderr

    migrated_dir = tmp_path / "ops" / "feedback" / "_migrated"
    assert not migrated_dir.exists(), (
        f"--dry-run must not create _migrated/; found: {list(migrated_dir.glob('*'))}"
    )


def test_dry_run_prints_preview_summary(tmp_path):
    """--dry-run stdout includes item count, review-file count, and output dir."""
    journal = _make_channel_a(tmp_path)
    b_dir = _make_channel_b_dir(tmp_path)

    result = run_migrate(tmp_path, channel_a=journal, channel_b_dir=b_dir, dry_run=True)
    assert result.returncode == 0, result.stderr

    out = result.stdout
    # Expect counts (3 items, 2 review files for the 2 groups quorum:2026-04-28 + exec.atlas-dev:2026-05-17)
    assert "3" in out, f"expected item count '3' in dry-run output: {out!r}"
    assert "dry" in out.lower() or "would" in out.lower(), (
        f"expected 'dry' or 'would' in output to distinguish from real run: {out!r}"
    )


# --- #9: collision-safe ids + clean index rebuild ---

_COLLIDE_FM = """\
---
emitter: exec.atlas-dev
skill_id: exec.atlas-dev
emitted_at: 2026-05-17T06:20:00Z
_draft: false
status: ok
severity: low
friction_note: "collision fixture"
suggested_fix: "address it"
---
body
"""


def test_migrate_channel_b_ids_unique_within_review(tmp_path):
    """Two channel-B emissions in one emitter+date group whose filenames collide
    in the first 20 chars must still get DISTINCT item ids — else triage --set
    patches only the first match, leaving the duplicate permanently open (#9)."""
    b_date = tmp_path / "skill-feedback" / "2026-05-17"
    b_date.mkdir(parents=True, exist_ok=True)
    # Both stems share the first 20 chars ("iris-landing-video-x").
    (b_date / "iris-landing-video-xx-alpha.md").write_text(_COLLIDE_FM)
    (b_date / "iris-landing-video-xx-beta.md").write_text(_COLLIDE_FM)

    result = run_migrate(tmp_path, channel_b_dir=tmp_path / "skill-feedback")
    assert result.returncode == 0, result.stderr

    migrated_dir = tmp_path / "ops" / "feedback" / "_migrated"
    ids = []
    for md in migrated_dir.glob("*.md"):
        meta, _ = fm_read(md)
        ids.extend(it["id"] for it in meta.get("items", []))
    assert len(ids) == 2, f"expected 2 items, got {ids}"
    assert len(set(ids)) == 2, f"item ids collided (dup never closes via --set): {ids}"
