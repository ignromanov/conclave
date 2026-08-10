"""Tests for briefing.scans 2.2 — spec_progress, roadmap, drift, project_digest.

All tests are hermetic: no live agent-memory/ tree is read or written.
tmp_path fixtures + VOIDPAY_AI_ROOT env override are used throughout.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from briefing.scans import ScanCtx, drift, project_digest, roadmap, spec_progress

# Live-instance tests: gated by the `live_instance` marker, whose conftest fixture points
# CONCLAVE_AI_ROOT at CONCLAVE_LIVE_INSTANCE_ROOT for marked tests only. The old form gated
# on CONCLAVE_AI_ROOT itself — a variable the hermetic conftest clears — so it was asking
# whether hermeticity had been switched off, and the answer was always no (GH#105).
_NEEDS_INSTANCE = pytest.mark.live_instance


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_ctx(tmp_path: Path, advisor: str = "kai-cto") -> ScanCtx:
    short = advisor.split("-")[0]
    return ScanCtx(
        advisor=advisor,
        short_name=short,
        repo_root=tmp_path,
        decisions_dir=tmp_path / "agent-memory" / "advisors" / "decisions",
        sessions_dir=tmp_path / "agent-memory" / "advisors" / "sessions",
        mentions_dir=tmp_path / "agent-memory" / "advisors" / "mentions",
        gh_cache_dir=tmp_path / "agent-memory" / "gh-cache",
        personality_path=tmp_path / ".claude" / "skills" / f"team.{advisor}" / "memory" / "personality.md",
        progress_path=tmp_path / "progress-summary.md",
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_spec(
    specs_root: Path,
    spec_id: str,
    title: str,
    advisor: str,
    status: str = "proposed",
    milestone: str = "",
    ac_block: str = "",
) -> Path:
    """Write a minimal spec.md fixture under specs_root/<spec_id>-slug/spec.md."""
    slug = f"{spec_id}-slug"
    spec_dir = specs_root / slug
    spec_dir.mkdir(parents=True, exist_ok=True)
    fm_lines = [
        "---",
        f"id: {spec_id}",
        f"title: \"{title}\"",
        f"status: {status}",
        f"advisor: {advisor}",
    ]
    if milestone:
        fm_lines.append(f"milestone: {milestone}")
    fm_lines.append("---")
    fm = "\n".join(fm_lines) + "\n\n"
    body = f"# Spec {spec_id}\n\n"
    if ac_block:
        body += f"## Acceptance criteria\n\n{ac_block}\n"
    _write(spec_dir / "spec.md", fm + body)
    return spec_dir / "spec.md"


# ---------------------------------------------------------------------------
# spec_progress
# ---------------------------------------------------------------------------

class TestSpecProgress:
    def test_missing_specs_dir_returns_placeholder(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        result = spec_progress.build(ctx)
        assert result == "_(no advisor-owned spec acceptance criteria found)_"

    def test_no_advisor_specs_returns_placeholder(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "001", "Some Spec", "nexus-ceo",
                   ac_block="- [x] done\n- [ ] open\n")
        result = spec_progress.build(ctx)
        assert result == "_(no advisor-owned spec acceptance criteria found)_"

    def test_counts_checkboxes_correctly(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "084", "My Spec", "kai-cto",
                   ac_block="- [x] AC1\n- [x] AC2\n- [ ] AC3\n")
        result = spec_progress.build(ctx)
        assert "2/3" in result
        assert "084" in result

    def test_spec_with_zero_checkboxes_omitted(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "001", "No AC spec", "kai-cto")
        result = spec_progress.build(ctx)
        assert result == "_(no advisor-owned spec acceptance criteria found)_"

    def test_advisor_owned_open_box_flagged(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        # Box body mentions the advisor name.
        ac = "- [ ] kai-cto should validate this\n- [x] done box\n"
        _make_spec(specs_root, "084", "Flagged Spec", "kai-cto", ac_block=ac)
        result = spec_progress.build(ctx)
        assert "★" in result

    def test_multiple_advisor_specs(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "010", "Alpha", "kai-cto",
                   ac_block="- [x] done\n")
        _make_spec(specs_root, "020", "Beta", "kai-cto",
                   ac_block="- [ ] open\n- [ ] open2\n")
        result = spec_progress.build(ctx)
        assert "010" in result
        assert "020" in result

    @_NEEDS_INSTANCE
    def test_real_data_does_not_crash(self, live_ctx) -> None:
        """Integration smoke: run against the live instance without writing anything."""
        result = spec_progress.build(live_ctx)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# roadmap
# ---------------------------------------------------------------------------

class TestRoadmap:
    def test_missing_specs_dir_returns_placeholder(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        result = roadmap.build(ctx)
        assert result == "_(no roadmap entries for advisor)_"

    def test_no_advisor_specs_returns_placeholder(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "001", "Other", "nexus-ceo")
        result = roadmap.build(ctx)
        assert result == "_(no roadmap entries for advisor)_"

    def test_renders_advisor_spec(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "084", "My Feature", "kai-cto",
                   status="in-progress", milestone="v1.2")
        result = roadmap.build(ctx)
        assert "084" in result
        assert "My Feature" in result
        assert "in-progress" in result
        assert "v1.2" in result

    def test_in_progress_sorted_before_proposed(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "001", "Proposed", "kai-cto", status="proposed")
        _make_spec(specs_root, "002", "InProgress", "kai-cto", status="in-progress")
        result = roadmap.build(ctx)
        lines = result.splitlines()
        assert "002" in lines[0]  # in-progress first
        assert "001" in lines[1]

    @_NEEDS_INSTANCE
    def test_real_data_does_not_crash(self, live_ctx) -> None:
        """Integration smoke: run against the live instance without writing anything."""
        result = roadmap.build(live_ctx)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# drift
# ---------------------------------------------------------------------------

def _make_registry(specs_root: Path, rows: list[tuple[str, str, str]]) -> None:
    """Write a minimal REGISTRY.md with table rows (id, title, status)."""
    header = (
        "# Specs Registry\n\n"
        "## Active\n\n"
        "| # | Feature | Status | Started | Milestone | Spec |\n"
        "|---|---------|--------|---------|-----------|------|\n"
    )
    body = ""
    for spec_id, title, status in rows:
        body += f"| {spec_id} | {title} | {status} | 2026-01-01 | — | — |\n"
    _write(specs_root / "REGISTRY.md", header + body)


class TestDrift:
    def test_missing_registry_returns_placeholder(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        specs_root.mkdir(parents=True)
        result = drift.build(ctx)
        assert result == "_(no spec/registry drift detected)_"

    def test_no_drift_returns_placeholder(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_registry(specs_root, [("84", "My Spec", "proposed")])
        _make_spec(specs_root, "084", "My Spec", "kai-cto", status="proposed")
        result = drift.build(ctx)
        assert result == "_(no spec/registry drift detected)_"

    def test_detects_drift(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        # Registry says DONE, spec.md says proposed.
        _make_registry(specs_root, [("84", "My Spec", "DONE")])
        _make_spec(specs_root, "084", "My Spec", "kai-cto", status="proposed")
        result = drift.build(ctx)
        assert "DRIFT" in result
        assert "084" in result
        assert "proposed" in result
        assert "done" in result

    def test_non_advisor_specs_ignored(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_registry(specs_root, [("1", "Other", "DONE")])
        _make_spec(specs_root, "001", "Other", "nexus-ceo", status="proposed")
        result = drift.build(ctx)
        assert result == "_(no spec/registry drift detected)_"

    def test_spec_not_in_registry_is_skipped(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_registry(specs_root, [])  # empty
        _make_spec(specs_root, "084", "My Spec", "kai-cto", status="proposed")
        result = drift.build(ctx)
        assert result == "_(no spec/registry drift detected)_"

    @_NEEDS_INSTANCE
    def test_real_data_does_not_crash(self, live_ctx) -> None:
        """Integration smoke: run against the live instance without writing anything."""
        result = drift.build(live_ctx)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# project_digest
# ---------------------------------------------------------------------------

_SAMPLE_PROGRESS = """\
# Progress Summary

> Compact version for CLAUDE.md @import.

**Phase**: P1 (Post-Launch) | **v1.0 DEPLOYED** Mar 28

**Recent**: 056-void-layer-codec Phase 1 DONE (May 19, 9 commits — repo init + skeleton), \
073-unified-in-app-browser-gate DONE (May 15, PR #236 squashed), \
074-agent-system-arch DONE (May 16, 11 commits — foundations migration)

**In Progress**: 039-onboarding-kit (growth), 040-competitor-comparison (growth)

**Next**: 056 Phase 2 — Rust impl (encode/decode + LEB128 varint)

**Tests**: 2,806 passing | 81%+ coverage
"""


class TestProjectDigest:
    def test_missing_file_returns_placeholder(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        result = project_digest.build(ctx)
        assert result == "_(progress-summary.md missing)_"

    def test_returns_bullet_list(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        _write(ctx.progress_path, _SAMPLE_PROGRESS)
        result = project_digest.build(ctx)
        lines = result.splitlines()
        assert all(line.startswith("- ") for line in lines if line)

    def test_at_most_5_bullets(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        _write(ctx.progress_path, _SAMPLE_PROGRESS)
        result = project_digest.build(ctx)
        assert len(result.splitlines()) <= 5

    def test_digest_shorter_than_source(self, tmp_path: Path) -> None:
        """Core AC: digest must be measurably smaller than the verbatim source."""
        ctx = make_ctx(tmp_path)
        _write(ctx.progress_path, _SAMPLE_PROGRESS)
        result = project_digest.build(ctx)
        assert len(result) < len(_SAMPLE_PROGRESS), (
            f"Digest ({len(result)} chars) not shorter than source ({len(_SAMPLE_PROGRESS)} chars)"
        )

    def test_contains_recent_spec_ids(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        _write(ctx.progress_path, _SAMPLE_PROGRESS)
        result = project_digest.build(ctx)
        # At least one spec id from **Recent** should appear.
        assert any(sid in result for sid in ("056", "073", "074"))

    @_NEEDS_INSTANCE
    def test_real_progress_summary_is_smaller(self, live_ctx) -> None:
        """Integration: the digest of a real progress-summary.md is shorter than its source.

        Optional DATA, so the absent branch asserts the documented placeholder instead of
        skipping — no instance in this project has ever had the file, which is exactly how
        this test spent a month reporting nothing."""
        result = project_digest.build(live_ctx)
        if not live_ctx.progress_path.is_file():
            assert result == "_(progress-summary.md missing)_"
            return
        source_len = len(live_ctx.progress_path.read_text(encoding="utf-8"))
        assert result != "_(progress-summary.md missing)_"
        assert len(result) < source_len, (
            f"Digest ({len(result)}) not shorter than source ({source_len})"
        )
