"""Tests for briefing.scans.plans — the plans inventory (spec 116 P1, GH#183).

The load-bearing assertion in this file is `test_a_plans_own_claim_is_never_read`: the
issue that commissioned this section was filed because two of four plan status headers
read by hand were false, so a plan's prose about itself must not be able to move the
number. Everything else here is ordinary coverage.
"""
from __future__ import annotations

from pathlib import Path

from briefing.scans import ScanCtx, plans


def make_ctx(tmp_path: Path, advisor: str = "kai-cto") -> ScanCtx:
    return ScanCtx(
        advisor=advisor,
        short_name=advisor.split("-")[0],
        repo_root=tmp_path / "data",
        decisions_dir=tmp_path / "data" / "decisions",
        sessions_dir=tmp_path / "data" / "sessions",
        mentions_dir=tmp_path / "data" / "mentions",
        gh_cache_dir=tmp_path / "data" / "gh-cache",
        personality_path=tmp_path / "persona.md",
        project_root=tmp_path / "code",
        plans_dir=tmp_path / "code" / ".claude" / "plans",
    )


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _spec_plan(ctx: ScanCtx, slug: str, body: str = "A plan.\n", name: str = "plan.md") -> Path:
    return _write(ctx.repo_root / "ops" / "specs" / slug / name, body)


def _verify_fm(kind: str, **kw: str) -> str:
    lines = ["---", "verify:", f"  kind: {kind}"]
    lines += [f"  {k}: {v}" for k, v in kw.items()]
    lines += ["---", "", "Body prose.", ""]
    return "\n".join(lines)


class TestDiscovery:
    def test_no_plans_returns_placeholder(self, tmp_path: Path) -> None:
        assert plans.build(make_ctx(tmp_path)) == "_(no plans found)_"

    def test_finds_both_conventions(self, tmp_path: Path) -> None:
        """A6 — the DATA convention and the harness convention, in one count.

        Hardcoding either one renders 0 in the other instance; the issue was filed from
        the instance that uses `.claude/plans/`, and this project uses the other.
        """
        ctx = make_ctx(tmp_path)
        _spec_plan(ctx, "116-a")
        _write(ctx.plans_dir / "2026-08-19-date-range.md", "Loose plan.\n")
        _write(ctx.plans_dir / "2026-08-20-nested" / "00-STATE.md", "Nested plan.\n")

        out = plans.build(ctx)
        assert out.startswith("3 plans — "), out

    def test_non_markdown_entries_are_not_plans(self, tmp_path: Path) -> None:
        """An inflated denominator is its own kind of lie."""
        ctx = make_ctx(tmp_path)
        _write(ctx.plans_dir / "real.md", "A plan.\n")
        _write(ctx.plans_dir / "neon-dump-queries.sql", "SELECT 1;\n")
        _write(ctx.plans_dir / "adslot.patch", "diff --git\n")

        assert plans.build(ctx).startswith("1 plan — ")

    def test_singular_noun_for_one_plan(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        _spec_plan(ctx, "116-a")
        assert plans.build(ctx).startswith("1 plan — ")


class TestDerivedState:
    def test_landed_when_predicate_holds(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        _write(ctx.project_root / "src" / "thing.py", "def clamp_date_range():\n    pass\n")
        _spec_plan(ctx, "116-a", _verify_fm("file-contains", file="src/thing.py",
                                            pattern="clamp_date_range"))
        out = plans.build(ctx)
        assert "1 landed" in out
        assert "0 open" in out and "0 unverifiable" in out

    def test_open_when_predicate_does_not_hold(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        _write(ctx.project_root / "src" / "thing.py", "def something_else():\n    pass\n")
        _spec_plan(ctx, "116-a", _verify_fm("file-contains", file="src/thing.py",
                                            pattern="clamp_date_range"))
        out = plans.build(ctx)
        assert "1 open" in out
        assert "- open (1) —" in out

    def test_broken_when_the_oracle_file_is_gone(self, tmp_path: Path) -> None:
        """'cannot confirm' and 'not done yet' are different facts, so they are
        different states — the tri-state comes from feedback_verify, not from us."""
        ctx = make_ctx(tmp_path)
        ctx.project_root.mkdir(parents=True, exist_ok=True)
        _spec_plan(ctx, "116-a", _verify_fm("file-contains", file="src/vanished.py",
                                            pattern="anything"))
        out = plans.build(ctx)
        assert "1 broken" in out

    def test_unverifiable_when_no_predicate_declared(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        _spec_plan(ctx, "116-a", "---\nowner: kai-cto\n---\n\nNo verify block.\n")
        out = plans.build(ctx)
        assert "1 unverifiable" in out
        assert "add one to its frontmatter" in out

    def test_a_plans_own_claim_is_never_read(self, tmp_path: Path) -> None:
        """A5 — the whole point of GH#183.

        Reproduces both falsifications on record. One plan's prose insists it is DONE
        and merged; another insists nothing was ever started. Neither declares a
        closing condition, so BOTH are `unverifiable` and NEITHER is landed or open:
        the prose has no route into the count.
        """
        ctx = make_ctx(tmp_path)
        _spec_plan(ctx, "116-a", "# STATE\n\nDONE — shipped, merged to main, PR closed.\n")
        _spec_plan(ctx, "116-b", "# STATE\n\nNo code written yet. Branch not cut yet.\n")

        out = plans.build(ctx)
        assert "2 unverifiable" in out
        assert "0 landed" in out
        assert "0 open" in out
        assert "DONE" not in out
        assert "Branch not cut" not in out

    def test_malformed_predicate_is_broken_not_unverifiable(self, tmp_path: Path) -> None:
        """Declared-but-unusable is a different fact from never-declared."""
        ctx = make_ctx(tmp_path)
        ctx.project_root.mkdir(parents=True, exist_ok=True)
        # file-contains requires both file and pattern; this gives neither
        _spec_plan(ctx, "116-a", "---\nverify:\n  kind: file-contains\n---\n\nBody.\n")
        out = plans.build(ctx)
        assert "1 broken" in out
        assert "0 unverifiable" in out


class TestRender:
    def test_zeros_render_with_their_scope_noun(self, tmp_path: Path) -> None:
        """A7 — on an inventory surface an omitted row is not a green signal.

        `output-formatting.md` §1 omits zero-state rows; that rule stops at the session
        summary's edge. Here '0 landed' is the finding, and every count carries the noun
        it counts.
        """
        ctx = make_ctx(tmp_path)
        _spec_plan(ctx, "116-a")
        first = plans.build(ctx).splitlines()[0]
        assert first == "1 plan — 0 landed · 0 open · 0 broken · 1 unverifiable"

    def test_proof_path_is_present(self, tmp_path: Path) -> None:
        """Every count is one hop from the command that reproduces it."""
        ctx = make_ctx(tmp_path)
        _spec_plan(ctx, "116-a")
        assert "`ops/specs/*/plan*.md`" in plans.build(ctx)

    def test_a_state_covering_everything_gets_no_member_list(self, tmp_path: Path) -> None:
        """Naming five arbitrary members of a group that IS the corpus adds nothing the
        count and the glob do not already carry."""
        ctx = make_ctx(tmp_path)
        for i in range(8):
            _spec_plan(ctx, f"116-{i}")
        out = plans.build(ctx)
        assert "- unverifiable (8) —" in out
        assert "›" not in out, out

    def test_a_minority_state_names_its_members(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        _write(ctx.project_root / "src" / "thing.py", "clamp\n")
        for i in range(4):
            _spec_plan(ctx, f"116-ok-{i}", _verify_fm("file-contains", file="src/thing.py",
                                                      pattern="clamp"))
        _spec_plan(ctx, "116-bad", _verify_fm("file-contains", file="src/thing.py",
                                              pattern="absent-marker"))
        out = plans.build(ctx)
        assert "- open (1) —" in out
        assert "› ops/specs/116-bad/plan.md" in out

    def test_member_list_is_capped_with_an_overflow_count(self, tmp_path: Path) -> None:
        ctx = make_ctx(tmp_path)
        _write(ctx.project_root / "src" / "thing.py", "clamp\n")
        # 20 landed (never listed), 7 open (listed, capped at 5 + overflow)
        for i in range(20):
            _spec_plan(ctx, f"116-ok-{i}", _verify_fm("file-contains", file="src/thing.py",
                                                      pattern="clamp"))
        for i in range(7):
            _spec_plan(ctx, f"116-bad-{i}", _verify_fm("file-contains", file="src/thing.py",
                                                       pattern="absent-marker"))
        out = plans.build(ctx)
        assert "- open (7) —" in out
        assert out.count("  › ops/") == 5, out
        assert "› … and 2 more" in out
        # `landed` is a count and never a row — the inverted pyramid
        assert "116-ok-0" not in out

    def test_all_clear_states_success_in_words(self, tmp_path: Path) -> None:
        """`git status`'s 'working tree clean' convention — success is stated, not implied."""
        ctx = make_ctx(tmp_path)
        _write(ctx.project_root / "src" / "thing.py", "clamp\n")
        _spec_plan(ctx, "116-a", _verify_fm("file-contains", file="src/thing.py",
                                            pattern="clamp"))
        out = plans.build(ctx)
        assert "Every plan's closing condition holds." in out


class TestPlansIsMountedInTheBriefing:
    def test_render_wires_the_section(self) -> None:
        """GH#183's own closing condition keys on render.py, not on this module — a scan
        that exists and is never rendered leaves the briefing exactly as it was."""
        from briefing import render

        src = Path(render.__file__).read_text(encoding="utf-8")
        assert '"plans": plans.build(ctx)' in src

    def test_template_has_the_placeholder(self) -> None:
        from briefing.paths import templates_dir

        tpl = (templates_dir() / "briefing.md").read_text(encoding="utf-8")
        assert "{{plans}}" in tpl
        assert "## Plans" in tpl
