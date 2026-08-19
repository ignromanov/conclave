"""Tests for Phase 2.1 scan modules: current_work, owed, interrupted.

Hermetic: all tests use tmp_path or monkeypatched CONCLAVE_AI_ROOT.
No test reads or writes the live agent-memory/ tree.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Live-instance tests: gated by the `live_instance` marker, whose conftest fixture points
# CONCLAVE_AI_ROOT at CONCLAVE_LIVE_INSTANCE_ROOT for marked tests only. The old form gated
# on CONCLAVE_AI_ROOT itself — a variable the hermetic conftest clears — so it was asking
# whether hermeticity had been switched off, and the answer was always no (GH#105).
_NEEDS_INSTANCE = pytest.mark.live_instance

from briefing.scans import ScanCtx, current_work, interrupted, owed

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
    name: str,
    status: str = "in_progress",
    advisor: str = "kai-cto",
    title: str = "Test Spec",
) -> Path:
    spec_dir = specs_root / name
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_md = spec_dir / "spec.md"
    spec_md.write_text(
        f"---\nid: {name}\ntitle: {title!r}\nstatus: {status}\nadvisor: {advisor}\n---\n\nBody.\n",
        encoding="utf-8",
    )
    return spec_md


def _make_plan(spec_dir: Path, checkboxes: list[tuple[bool, str]]) -> Path:
    plan_md = spec_dir / "plan.md"
    lines = ["# Plan\n"]
    for done, text in checkboxes:
        mark = "x" if done else " "
        lines.append(f"- [{mark}] {text}")
    plan_md.write_text("\n".join(lines), encoding="utf-8")
    return plan_md


# ===========================================================================
# current_work
# ===========================================================================


class TestCurrentWork:
    def test_placeholder_when_no_specs_dir(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        result = current_work.build(ctx)
        assert "_(no active work detected)_" in result

    def test_placeholder_when_no_active_specs(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "001-done", status="done")
        result = current_work.build(ctx)
        assert "_(no active work detected)_" in result

    def test_active_spec_appears(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "084-test", status="in_progress", title="My Feature")
        result = current_work.build(ctx)
        assert "084-test" in result
        assert "My Feature" in result

    def test_plan_checkbox_progress(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        spec_md = _make_spec(specs_root, "084-test", status="in_progress")
        _make_plan(
            spec_md.parent,
            [(True, "Done step"), (False, "Next step"), (False, "Later step")],
        )
        result = current_work.build(ctx)
        assert "1/3 tasks done" in result

    def test_next_unchecked_task(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        spec_md = _make_spec(specs_root, "084-test", status="in_progress")
        _make_plan(
            spec_md.parent,
            [(True, "Finished step"), (False, "The next task"), (False, "Another")],
        )
        result = current_work.build(ctx)
        assert "The next task" in result

    def test_commits_block_present_when_git_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = make_ctx(tmp_path)
        # Inject fake git log via git-cache file.
        cache_log = tmp_path / "agent-memory" / "git-cache" / "log.md"
        _write(
            cache_log,
            "abc1234 feat(084): implement phase 2\ndef5678 fix: patch something\n",
        )
        result = current_work.build(ctx)
        assert "Recent commits" in result
        assert "feat(084)" in result

    def test_task_ids_parsed_from_commits(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        cache_log = tmp_path / "agent-memory" / "git-cache" / "log.md"
        _write(cache_log, "abc1234 chore(084): T2.1 implement scans\n")
        result = current_work.build(ctx)
        # Task-ID pattern should be extracted.
        assert "084" in result or "2.1" in result

    def test_only_advisor_owned_specs(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, advisor="kai-cto")
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "001-kai", status="in_progress", advisor="kai-cto")
        _make_spec(specs_root, "002-nexus", status="in_progress", advisor="nexus-ceo")
        result = current_work.build(ctx)
        assert "001-kai" in result
        assert "002-nexus" not in result

    @_NEEDS_INSTANCE
    def test_real_data_produces_string(self, live_ctx) -> None:
        """Integration smoke: build() returns a non-empty string from the live instance."""
        result = current_work.build(live_ctx)
        assert isinstance(result, str)
        assert len(result) > 0


# ===========================================================================
# owed
# ===========================================================================


class TestOwed:
    def test_placeholder_when_no_specs_dir(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        result = owed.build(ctx)
        assert "_(no pending actions owed by you found in active specs)_" in result

    def test_placeholder_when_no_active_specs(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        specs_root = tmp_path / "ops" / "specs"
        _make_spec(specs_root, "001-done", status="done")
        result = owed.build(ctx)
        assert "_(no pending actions owed" in result

    def test_finds_advisor_name_in_unchecked_item(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, advisor="kai-cto")
        specs_root = tmp_path / "ops" / "specs"
        spec_md = _make_spec(specs_root, "084-test", status="in_progress", advisor="kai-cto")
        _write(
            spec_md.parent / "plan.md",
            "# Plan\n- [ ] kai-cto reviews the design\n- [x] done already\n",
        )
        result = owed.build(ctx)
        assert "kai-cto reviews the design" in result

    def test_finds_short_name_in_unchecked_item(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, advisor="kai-cto")
        specs_root = tmp_path / "ops" / "specs"
        spec_md = _make_spec(specs_root, "084-test", status="in_progress", advisor="kai-cto")
        _write(
            spec_md.parent / "plan.md",
            "# Plan\n- [ ] kai validates the output\n",
        )
        result = owed.build(ctx)
        assert "kai validates the output" in result

    def test_ignores_checked_items(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, advisor="kai-cto")
        specs_root = tmp_path / "ops" / "specs"
        spec_md = _make_spec(specs_root, "084-test", status="in_progress", advisor="kai-cto")
        _write(
            spec_md.parent / "plan.md",
            "# Plan\n- [x] kai-cto already did this\n",
        )
        result = owed.build(ctx)
        assert "_(no pending actions owed" in result

    def test_ignores_non_active_specs(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path, advisor="kai-cto")
        specs_root = tmp_path / "ops" / "specs"
        spec_md = _make_spec(specs_root, "001-done", status="done", advisor="kai-cto")
        _write(
            spec_md.parent / "plan.md",
            "# Plan\n- [ ] kai-cto do something\n",
        )
        result = owed.build(ctx)
        assert "_(no pending actions owed" in result

    @_NEEDS_INSTANCE
    def test_real_data_produces_string(self, live_ctx) -> None:
        """Integration smoke: build() returns a non-empty string from the live instance."""
        result = owed.build(live_ctx)
        assert isinstance(result, str)
        assert len(result) > 0


# ===========================================================================
# interrupted
# ===========================================================================


def _make_handoff(
    handoffs_dir: Path,
    name: str,
    status: str = "open",
    content_extra: str = "",
) -> Path:
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    md = handoffs_dir / f"{name}.md"
    md.write_text(
        f"---\ntype: handoff\nstatus: {status}\nfrom: kai-cto\nto: atlas\n---\n\n"
        f"Resume from here.{content_extra}\n",
        encoding="utf-8",
    )
    return md


class TestInterrupted:
    def test_placeholder_when_no_handoffs_dir(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        result = interrupted.build(ctx)
        assert "_(no interrupted work / open resume-prompts found)_" in result

    def test_placeholder_when_all_terminal(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        handoffs = tmp_path / "ops" / "handoffs"
        _make_handoff(handoffs, "2026-05-01-old", status="complete")
        _make_handoff(handoffs, "2026-05-02-done", status="done")
        result = interrupted.build(ctx)
        assert "_(no interrupted work / open resume-prompts found)_" in result

    def test_open_handoff_appears(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        handoffs = tmp_path / "ops" / "handoffs"
        _make_handoff(handoffs, "2026-05-20-resume", status="open")
        result = interrupted.build(ctx)
        assert "2026-05-20-resume.md" in result
        assert "open" in result

    def test_shows_mtime_and_status(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        handoffs = tmp_path / "ops" / "handoffs"
        _make_handoff(handoffs, "2026-05-20-x", status="pending")
        result = interrupted.build(ctx)
        assert "pending" in result
        assert "UTC" in result  # mtime includes UTC suffix

    def test_max_five_items(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        handoffs = tmp_path / "ops" / "handoffs"
        for i in range(8):
            _make_handoff(handoffs, f"2026-05-{i + 1:02d}-h{i}", status="open")
        result = interrupted.build(ctx)
        assert result.count("\n- ") <= 4  # 5 items = 5 lines starting with "- "
        # Count leading "- " lines.
        item_lines = [ln for ln in result.splitlines() if ln.startswith("- ")]
        assert len(item_lines) <= 5

    def test_excludes_index_md(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        handoffs = tmp_path / "ops" / "handoffs"
        handoffs.mkdir(parents=True, exist_ok=True)
        (handoffs / "INDEX.md").write_text("# Index\n", encoding="utf-8")
        result = interrupted.build(ctx)
        assert "INDEX.md" not in result
        assert "_(no interrupted work" in result

    @_NEEDS_INSTANCE
    def test_real_data_produces_string(self, live_ctx) -> None:
        """Integration smoke: build() returns a non-empty string from the live instance."""
        result = interrupted.build(live_ctx)
        assert isinstance(result, str)
        assert len(result) > 0
