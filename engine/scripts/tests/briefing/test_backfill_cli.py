"""Tests for briefing.backfill_cli — CLI argument parsing and safety gate.

All tests that invoke --apply --confirm use a fixture tmp repo, never the live tree.
"""
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from briefing.backfill_cli import main
from briefing.paths import repo_root


def _refuse_to_migrate_anything_but(expected: Path) -> None:
    """Abort before the write if the migration would target anything but `expected`.

    This is the only place in the suite that invokes a destructive DATA migration
    IN-PROCESS; every sibling (`test_frontmatter_backfill.py`, `test_advisor_rename.py`)
    goes through `run_engine`, a subprocess with an explicit environment. In-process is
    the shape that can be silently mis-targeted, because the patch and the resolver read
    the same live `os.environ` and `patch.dict` with a mapping ADDS keys rather than
    clearing them.

    It has cost 34 DATA files once (GH#116): the test patched the retired `VOIDPAY_AI_ROOT`
    alias, which only applies when `CONCLAVE_AI_ROOT` is absent, and the SessionStart hook
    exports `CONCLAVE_AI_ROOT` unconditionally. `--apply --confirm` migrated the operator's
    memory — 16 decisions and 18 session records.

    The test DID fail that day, on its post-write read. That is the distinction this helper
    exists for: a check that runs after the write is a detector, and by then the tracked
    files are already rewritten. The same question asked one line earlier is a gate.

    It calls `repo_root` — the resolver `backfill_cli.main` itself calls — rather than
    re-deriving the answer. A re-implementation would agree with itself while the tool
    resolved elsewhere, which is the exact failure being guarded against.

    Honest about its own reach: the 2026 incident is no longer reproducible in-suite, because
    the topmost conftest scrubs every instance-root variable per test (#242), so no ambient
    `CONCLAVE_AI_ROOT` survives to shadow a patch. This is the second layer. The conftest
    should not be the only thing between a destructive test and the operator's memory.
    """
    resolved = repo_root()
    assert resolved == expected.resolve(), (
        f"refusing to run --apply --confirm: the migration resolves its DATA root to "
        f"{resolved}, not the fixture tree {expected.resolve()}. Something shadowed the "
        f"patched CONCLAVE_AI_ROOT, and the next line rewrites every record under that root."
    )


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

        with patch.dict("os.environ", {"CONCLAVE_AI_ROOT": str(tmp_path)}):
            _refuse_to_migrate_anything_but(tmp_path)
            rc = main(["--apply", "--confirm"])

        assert rc == 0
        migrated = (decisions / "2026-05-20-kai-legacy.md").read_text()
        assert "schema_version: 1" in migrated
        assert "type: decision" in migrated

    def test_a_shadowed_patch_aborts_before_the_migration_runs(self, tmp_path: Path):
        """The gate fires on a mis-targeted root, and fires BEFORE anything is written.

        Measured, not assumed. The same shadowed patch driven straight into
        `main(["--apply", "--confirm"])` with no assertion in front of it rewrote the decoy
        record — `slug`/`date`/`by` became `type`/`id`/`created`/`owner`/`schema_version` —
        and returned **rc = 0**, printing `mode=APPLIED`. The migration does not merely fail
        to notice the wrong target; it reports success against it. That is the 34-file
        incident in miniature, and it is why this assertion sits one line ABOVE the call
        rather than joining the post-write read that already existed.
        """
        decoy = tmp_path / "decoy"
        (decoy / "agent-memory" / "advisors" / "decisions").mkdir(parents=True)
        record = decoy / "agent-memory" / "advisors" / "decisions" / "2026-05-20-x.md"
        original = textwrap.dedent("""\
            ---
            slug: legacy
            date: 2026-05-20
            by: kai-cto
            ---
            Body.
            """)
        record.write_text(original, encoding="utf-8")
        intended = tmp_path / "intended"
        intended.mkdir()

        with patch.dict("os.environ", {"CONCLAVE_AI_ROOT": str(decoy)}):
            with pytest.raises(AssertionError) as caught:
                _refuse_to_migrate_anything_but(intended)

        assert str(decoy.resolve()) in str(caught.value), (
            "the refusal must name the root it would have migrated"
        )
        assert record.read_text(encoding="utf-8") == original, (
            "the gate let a write through — it is a detector, not a gate"
        )


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

        One variable is now enough. This call reaches both `briefing.paths` and
        `enginelib.paths`, which used to be two implementations honouring two
        different sets of env names: the alias pinned one of them while the other
        fell back to CLAUDE_PROJECT_DIR/.conclave, so on a dev box the ambient
        instance root stood in for the tmp one and the isolation only appeared to
        hold — the test failed the first time CI ran it without that variable.
        `briefing.paths` re-exports `enginelib.paths` now; pinning CONCLAVE_AI_ROOT
        pins every reader.
        """
        from unittest.mock import patch

        from briefing.__main__ import main as briefing_main
        with patch.dict("os.environ", {"CONCLAVE_AI_ROOT": str(kai_cto_tmp_root)}):
            rc = briefing_main(["kai-cto"])
        assert rc == 0
        # Confirm output was written under the tmp root, not the live tree.
        out = kai_cto_tmp_root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
        assert out.is_file(), f"Output not written under tmp root: {out}"
