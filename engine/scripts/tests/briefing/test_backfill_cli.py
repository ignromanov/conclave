"""Tests for briefing.backfill_cli — CLI argument parsing and safety gate.

All tests that invoke --apply --confirm use a fixture tmp repo, never the live tree.
"""
import textwrap
from pathlib import Path
from unittest.mock import patch

from briefing.backfill_cli import main


class TestBackfillCliDryRun:
    def test_dry_run_flag_exits_zero(self):
        rc = main(["--dry-run"])
        assert rc == 0

    def test_no_args_exits_zero(self):
        # Default is dry-run; safe to run without flags.
        rc = main([])
        assert rc == 0


class TestBackfillCliSafetyGate:
    def test_apply_without_confirm_exits_nonzero(self, capsys):
        rc = main(["--apply"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "--confirm" in captured.err

    def test_apply_with_confirm_uses_fixture_tree(self, tmp_path: Path):
        """--apply --confirm against a fixture repo (not the live .ai/ tree)."""
        # Build a minimal fake repo structure.
        (tmp_path / "ops").mkdir()
        (tmp_path / ".claude").mkdir()
        decisions = tmp_path / "agent-memory" / "advisors" / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "2026-05-20-kai-legacy.md").write_text(
            textwrap.dedent("""\
            ---
            slug: legacy
            date: 2026-05-20
            by: kai-cto
            status: active
            ---
            Body.
            """),
            encoding="utf-8",
        )

        import briefing.paths as _paths
        with patch.object(_paths, "_REPO_ROOT_CACHE", None):
            with patch.dict("os.environ", {"VOIDPAY_AI_ROOT": str(tmp_path)}):
                rc = main(["--apply", "--confirm"])

        assert rc == 0
        migrated = (decisions / "2026-05-20-kai-legacy.md").read_text()
        assert "schema_version: 1" in migrated
        assert "type: decision" in migrated


class TestMainEntrypoint:
    def test_main_module_importable(self):
        import briefing.__main__ as m
        assert callable(m.main)

    def test_unknown_advisor_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        from briefing.__main__ import main as briefing_main
        # Non-empty registry → an id absent from it is rejected (permissive only when empty).
        (tmp_path / ".claude" / "skills" / "team.kai-cto").mkdir(parents=True)
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
        rc = briefing_main(["not-an-advisor"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "not in the instance registry" in captured.err

    def test_known_advisor_exits_zero(self, capsys, kai_cto_tmp_root):
        """briefing_main(["kai-cto"]) must run against an isolated tmp tree.

        Without root isolation this test overwrites the live
        agent-memory/advisors/briefings/kai-cto.md on every pytest run.
        The kai_cto_tmp_root fixture (conftest.py) seeds a hermetic .ai-like
        root and both resolvers are pointed at it for the duration of the call.

        Two resolvers must be pinned, not one. `briefing.paths` honours the
        VOIDPAY_AI_ROOT back-compat alias, but `enginelib.paths.repo_root` —
        which this call also reaches — knows only CONCLAVE_AI_ROOT, and falls
        back to CLAUDE_PROJECT_DIR/.conclave when it is unset. That fallback is
        why the isolation appeared to work: a dev box has CLAUDE_PROJECT_DIR, so
        the ambient instance root stood in for the tmp one, and the test only
        failed once CI ran it where no such var exists.
        """
        from unittest.mock import patch

        import briefing.paths as _paths
        from briefing.__main__ import main as briefing_main
        with patch.object(_paths, "_REPO_ROOT_CACHE", None):
            with patch.dict("os.environ", {
                "VOIDPAY_AI_ROOT": str(kai_cto_tmp_root),
                "CONCLAVE_AI_ROOT": str(kai_cto_tmp_root),
            }):
                rc = briefing_main(["kai-cto"])
        assert rc == 0
        # Confirm output was written under the tmp root, not the live tree.
        out = kai_cto_tmp_root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
        assert out.is_file(), f"Output not written under tmp root: {out}"
