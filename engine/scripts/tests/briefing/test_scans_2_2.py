"""Tests for briefing.scans 2.2 — spec_progress, roadmap, drift.

All tests are hermetic: no live agent-memory/ tree is read or written.
tmp_path fixtures + CONCLAVE_AI_ROOT env override are used throughout.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from briefing.scans import ScanCtx, drift, roadmap, spec_progress

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
        project_root=tmp_path,
        plans_dir=tmp_path / ".claude" / "plans",
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
    ac_heading: str = "## Acceptance criteria",
    ac_heading_only: bool = False,
    owner: str = "",
    owner_suggestion: str = "",
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
    ]
    # An empty value omits the line: 23 of 28 real specs carry `owner` and no
    # `advisor`, a shape no fixture could express while `advisor` was mandatory.
    if advisor:
        fm_lines.append(f"advisor: {advisor}")
    if owner:
        fm_lines.append(f"owner: {owner}")
    if owner_suggestion:
        fm_lines.append(f"owner_suggestion: {owner_suggestion}")
    if milestone:
        fm_lines.append(f"milestone: {milestone}")
    fm_lines.append("---")
    fm = "\n".join(fm_lines) + "\n\n"
    body = f"# Spec {spec_id}\n\n"
    if ac_block or ac_heading_only:
        body += f"{ac_heading}\n\n{ac_block}\n"
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

    @pytest.mark.parametrize("heading", [
        "## 4. Acceptance",                                   # spec 115
        "## Acceptance",                                      # bare
        "## Acceptance (draft — refined in plan)",            # spec 091
        "## 8. Acceptance criteria",                          # spec 103
        "## 5. Acceptance and kill criteria (measurable)",    # spec 117
        "## 7. Acceptance sketch (P1, red-first)",            # spec 106
    ])
    def test_numbered_and_bare_acceptance_headings_are_counted(
        self, tmp_path: Path, heading: str
    ) -> None:
        """The corpus writes ten spellings of the heading; the regex matched one (#227).

        `^##\\s+acceptance criteria` misses `## 4. Acceptance` and every numbered or
        parenthesised variant. Nine of the twenty-one specs carrying an acceptance
        block were invisible to the counter, spec 115's four checkboxes among them.
        """
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "115", "State report", "kai-cto",
                   ac_block="- [x] AC1\n- [x] AC2\n- [ ] AC3\n- [ ] AC4\n",
                   ac_heading=heading)
        result = spec_progress.build(ctx)
        assert "2/4" in result, result

    def test_acceptance_block_with_no_checkboxes_renders_unverifiable(
        self, tmp_path: Path
    ) -> None:
        """A spec that declares acceptance and lists no boxes is unverifiable, not absent.

        Zero and absent are different states: twelve specs carry an acceptance heading
        with no checkbox under it, and dropping them renders identically to owning no
        specs at all — which is what the advisor concludes.
        """
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "117", "Session ledger", "kai-cto",
                   ac_block="Prose, no boxes.\n", ac_heading="## 5. Acceptance")
        result = spec_progress.build(ctx)
        assert "unverifiable" in result, result
        assert "117" in result

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


class TestFrontmatterScalars:
    def test_double_quoted_title_with_inner_quotes_survives(self, tmp_path: Path) -> None:
        """`.strip('"')` eats one quote too many and leaves the escape behind (#226).

        Spec 107's title is `"… truth for \\"who is an advisor\\""`. Stripping the
        quote CHARACTER from both ends removes the closing pair and renders
        `… truth for \\"who is an advisor\\` — invisible while the section never
        rendered a row, visible the moment it did.
        """
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        spec_dir = specs_root / "107-slug"
        spec_dir.mkdir(parents=True)
        (spec_dir / "spec.md").write_text(
            '---\nid: 107\n'
            'title: "Advisor identity registry — truth for \\"who is an advisor\\""\n'
            'status: proposed\nowner: kai-cto\n---\n\n# Spec 107\n',
            encoding="utf-8",
        )
        result = roadmap.build(ctx)
        assert 'truth for "who is an advisor"' in result, result
        assert "\\" not in result, result


class TestOwnershipInclusion:
    """#226 — a spec is the advisor's when ANY ownership field names them.

    `owner` is the field REGISTRY.md and 23 of 28 specs actually carry; the scans
    read only `advisor` and `owner_suggestion`, so sage-cto owned 102/107/111/117
    and every one of these sections rendered its empty placeholder.
    """

    def test_spec_progress_includes_owner_only_spec(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "102", "Web dashboard", advisor="",
                   owner="kai-cto", ac_block="- [x] one\n- [ ] two\n")
        result = spec_progress.build(ctx)
        assert "102" in result, result
        assert "1/2" in result

    def test_roadmap_includes_owner_only_spec(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "107", "Identity registry", advisor="", owner="kai-cto")
        result = roadmap.build(ctx)
        assert "107" in result, result

    def test_drift_includes_owner_only_spec(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_registry(specs_root, [("111", "Notice channel", "DONE")])
        _make_spec(specs_root, "111", "Notice channel", advisor="",
                   owner="kai-cto", status="proposed")
        result = drift.build(ctx)
        assert "DRIFT" in result, result

    def test_row_names_the_field_that_matched(self, tmp_path: Path) -> None:
        """A pointer travels with its referent: which field claimed this spec."""
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "102", "Web dashboard", advisor="",
                   owner="kai-cto", ac_block="- [x] one\n")
        result = spec_progress.build(ctx)
        assert "owner:" in result, result

    def test_retired_engine_id_resolves_and_is_shown_as_inferred(
        self, tmp_path: Path
    ) -> None:
        """`forge` is the engine's own pre-106 id for forge-chro (#226)."""
        ctx = make_ctx(tmp_path, advisor="forge-chro")
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "104", "Constitution", advisor="",
                   owner="forge", ac_block="- [x] one\n")
        result = spec_progress.build(ctx)
        assert "104" in result, result
        assert "forge→forge-chro" in result

    def test_disagreeing_ownership_fields_are_both_rendered(
        self, tmp_path: Path
    ) -> None:
        """Twelve specs carry both fields and six disagree — collapsing them lies.

        093 is `owner: forge` and `advisor: quorum`. forge-chro must see the row AND
        see that a second field names someone else, rather than a confident single
        attribution.
        """
        ctx = make_ctx(tmp_path, advisor="forge-chro")
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "093", "Self-healing loop", advisor="quorum",
                   owner="forge", ac_block="- [x] one\n")
        result = spec_progress.build(ctx)
        assert "quorum" in result, result

    def test_spec_naming_nobody_relevant_stays_out(self, tmp_path: Path) -> None:
        """Widening the filter must not turn it into no filter at all."""
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "999", "Someone else", advisor="",
                   owner="nexus-ceo", ac_block="- [x] one\n")
        result = spec_progress.build(ctx)
        assert result == "_(no advisor-owned spec acceptance criteria found)_"


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


