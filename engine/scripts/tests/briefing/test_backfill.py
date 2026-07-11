"""Tests for briefing.backfill — legacy field mapping, idempotent, dry-run default."""
import textwrap
from pathlib import Path

import pytest

from briefing.backfill import BackfillPlan, backfill_dir, plan_dir

# ---------------------------------------------------------------------------
# Fixtures — write legacy-format files into tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture()
def decision_dir(tmp_path: Path) -> Path:
    """A decisions/ fixture directory with one legacy file."""
    d = tmp_path / "decisions"
    d.mkdir()

    # Legacy format: slug, date, by — no type, no schema_version
    (d / "2026-05-20-kai-cto-test-decision.md").write_text(
        textwrap.dedent("""\
        ---
        slug: test-decision
        date: 2026-05-20
        by: kai-cto
        status: active
        ---

        Body of the decision.
        """),
        encoding="utf-8",
    )
    return d


@pytest.fixture()
def decision_dir_already_migrated(tmp_path: Path) -> Path:
    """A decisions/ dir with a file that is already migrated (has schema_version)."""
    d = tmp_path / "decisions"
    d.mkdir()
    (d / "2026-05-20-kai-cto-migrated.md").write_text(
        textwrap.dedent("""\
        ---
        type: decision
        id: 2026-05-20-kai-cto-migrated
        owner: kai-cto
        created: 2026-05-20
        status: proposed
        confidence: high
        contested: false
        schema_version: 1
        ---

        Already migrated.
        """),
        encoding="utf-8",
    )
    return d


@pytest.fixture()
def mixed_dir(tmp_path: Path) -> Path:
    """A directory with one legacy + one already-migrated file."""
    d = tmp_path / "decisions"
    d.mkdir()

    (d / "2026-05-20-kai-cto-legacy.md").write_text(
        textwrap.dedent("""\
        ---
        slug: legacy
        date: 2026-05-20
        by: kai-cto
        status: active
        ---
        Legacy body.
        """),
        encoding="utf-8",
    )
    (d / "2026-05-20-nexus-ceo-modern.md").write_text(
        textwrap.dedent("""\
        ---
        type: decision
        id: 2026-05-20-nexus-ceo-modern
        owner: nexus-ceo
        created: 2026-05-20
        status: proposed
        confidence: high
        contested: false
        schema_version: 1
        ---
        Modern body.
        """),
        encoding="utf-8",
    )
    return d


# ---------------------------------------------------------------------------
# plan_dir — returns a BackfillPlan without mutating files
# ---------------------------------------------------------------------------

class TestPlanDir:
    def test_returns_backfill_plan(self, decision_dir: Path):
        plan = plan_dir(decision_dir, page_type="decision")
        assert isinstance(plan, BackfillPlan)

    def test_legacy_file_is_in_plan(self, decision_dir: Path):
        plan = plan_dir(decision_dir, page_type="decision")
        assert len(plan.to_migrate) == 1

    def test_already_migrated_file_not_in_plan(self, decision_dir_already_migrated: Path):
        plan = plan_dir(decision_dir_already_migrated, page_type="decision")
        assert len(plan.to_migrate) == 0

    def test_mixed_dir_only_legacy_in_plan(self, mixed_dir: Path):
        plan = plan_dir(mixed_dir, page_type="decision")
        assert len(plan.to_migrate) == 1
        assert "legacy" in plan.to_migrate[0].name

    def test_plan_does_not_mutate_files(self, decision_dir: Path):
        original = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        plan_dir(decision_dir, page_type="decision")
        after = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        assert original == after, "plan_dir must not mutate files"

    def test_plan_has_file_count(self, mixed_dir: Path):
        plan = plan_dir(mixed_dir, page_type="decision")
        assert plan.total_files == 2
        assert plan.skipped == 1


# ---------------------------------------------------------------------------
# backfill_dir — dry_run=True (default) mutates nothing
# ---------------------------------------------------------------------------

class TestBackfillDirDryRun:
    def test_dry_run_does_not_mutate(self, decision_dir: Path):
        original = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        backfill_dir(decision_dir, page_type="decision", dry_run=True)
        after = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        assert original == after, "dry_run=True must not write any files"

    def test_dry_run_returns_plan(self, decision_dir: Path):
        plan = backfill_dir(decision_dir, page_type="decision", dry_run=True)
        assert isinstance(plan, BackfillPlan)
        assert len(plan.to_migrate) == 1


# ---------------------------------------------------------------------------
# backfill_dir — dry_run=False applies the migration
# ---------------------------------------------------------------------------

class TestBackfillDirApply:
    def test_apply_adds_type(self, decision_dir: Path):
        backfill_dir(decision_dir, page_type="decision", dry_run=False)
        text = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        assert "type: decision" in text

    def test_apply_adds_schema_version(self, decision_dir: Path):
        backfill_dir(decision_dir, page_type="decision", dry_run=False)
        text = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        assert "schema_version: 1" in text

    def test_apply_maps_slug_to_id(self, decision_dir: Path):
        backfill_dir(decision_dir, page_type="decision", dry_run=False)
        text = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        assert "id:" in text
        # slug key must be gone
        assert "slug:" not in text

    def test_apply_maps_by_to_owner(self, decision_dir: Path):
        backfill_dir(decision_dir, page_type="decision", dry_run=False)
        text = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        assert "owner: kai-cto" in text
        assert "by:" not in text

    def test_apply_maps_date_to_created(self, decision_dir: Path):
        backfill_dir(decision_dir, page_type="decision", dry_run=False)
        text = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        assert "created: 2026-05-20" in text
        assert "\ndate:" not in text

    def test_apply_preserves_body(self, decision_dir: Path):
        backfill_dir(decision_dir, page_type="decision", dry_run=False)
        text = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()
        assert "Body of the decision." in text


# ---------------------------------------------------------------------------
# Idempotency — re-run on already-migrated files is a no-op
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_rerun_is_noop(self, decision_dir: Path):
        # First apply
        backfill_dir(decision_dir, page_type="decision", dry_run=False)
        after_first = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()

        # Second apply — must be identical
        backfill_dir(decision_dir, page_type="decision", dry_run=False)
        after_second = (decision_dir / "2026-05-20-kai-cto-test-decision.md").read_text()

        assert after_first == after_second, "Re-run must be idempotent"

    def test_rerun_plan_shows_zero_to_migrate(self, decision_dir: Path):
        backfill_dir(decision_dir, page_type="decision", dry_run=False)
        plan = plan_dir(decision_dir, page_type="decision")
        assert len(plan.to_migrate) == 0

    def test_already_migrated_not_touched(self, decision_dir_already_migrated: Path):
        original = (
            decision_dir_already_migrated / "2026-05-20-kai-cto-migrated.md"
        ).read_text()
        backfill_dir(decision_dir_already_migrated, page_type="decision", dry_run=False)
        after = (
            decision_dir_already_migrated / "2026-05-20-kai-cto-migrated.md"
        ).read_text()
        assert original == after, "Already-migrated file must not be touched"
