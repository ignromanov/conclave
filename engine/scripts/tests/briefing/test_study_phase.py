"""Tests for lifecycle/study-phase.py — team.done Study phase orchestrator."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import study_phase
from study_phase import StudyResult, run_study

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _make_root(tmp_path: Path) -> Path:
    (tmp_path / "ops").mkdir(parents=True, exist_ok=True)
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "kai-cto.md").write_text("---\n---\n")  # populate advisor registry
    return tmp_path


def _stub_wiki_dir(tmp_path: Path, scripts: dict[str, tuple[str, int]]) -> Path:
    """Create stub wiki scripts. scripts = {name: (stdout_body, exit_code)}."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    for name, (body, code) in scripts.items():
        script = wiki_dir / name
        script.write_text(
            f"#!/usr/bin/env bash\n{body}\nexit {code}\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
    return wiki_dir


# ---------------------------------------------------------------------------
# StudyResult
# ---------------------------------------------------------------------------

class TestStudyResult:
    def test_no_findings(self):
        r = StudyResult()
        assert not r.has_findings()
        assert not r.is_p0_blocking()
        assert r.summary_row() == ""

    def test_p0_blocking(self):
        r = StudyResult(stale_p0=1)
        assert r.is_p0_blocking()
        row = r.summary_row()
        assert "✗" in row
        assert "P0:1" in row

    def test_p1_stale_uses_warning_glyph(self):
        r = StudyResult(stale_p1=2)
        row = r.summary_row()
        assert "⚠" in row
        assert "P1:2" in row

    def test_zero_counters_omitted_from_row(self):
        r = StudyResult(captures=3, promoted=0, stale_p0=0, stale_p1=0, link_violations=0)
        row = r.summary_row()
        assert "promoted" not in row
        assert "stale" not in row
        assert "link" not in row
        assert "capture:3" in row

    def test_all_fields_present(self):
        r = StudyResult(captures=2, promoted=1, stale_p0=0, stale_p1=3, link_violations=4)
        row = r.summary_row()
        assert "capture:2" in row
        assert "promoted:1" in row
        assert "P1:3" in row
        assert "link:4" in row

    def test_has_findings_true_when_any_nonzero(self):
        assert StudyResult(captures=1).has_findings()
        assert StudyResult(promoted=1).has_findings()
        assert StudyResult(stale_p0=1).has_findings()
        assert StudyResult(stale_p1=1).has_findings()
        assert StudyResult(link_violations=1).has_findings()


# ---------------------------------------------------------------------------
# _parse_capture_count
# ---------------------------------------------------------------------------

class TestParseCaptureCount:
    def test_extracts_count(self):
        stdout = "✓ Capture suggestions (3/10) since HEAD~5:\n  - promote id1"
        assert study_phase._parse_capture_count(stdout) == 3

    def test_returns_zero_on_no_match(self):
        assert study_phase._parse_capture_count("✓ No capture candidates") == 0


# ---------------------------------------------------------------------------
# _parse_promote_ids
# ---------------------------------------------------------------------------

class TestParsePromoteIds:
    def test_extracts_ids(self):
        stdout = "  - promote 2026-05-20-test-decision (age: 2 days ago) — run: promote-decision.sh --id 2026-05-20-test-decision"
        ids = study_phase._parse_promote_ids(stdout)
        assert ids == ["2026-05-20-test-decision"]

    def test_multiple_ids(self):
        stdout = (
            "  - promote-decision.sh --id aaa\n"
            "  - promote-decision.sh --id bbb\n"
        )
        ids = study_phase._parse_promote_ids(stdout)
        assert ids == ["aaa", "bbb"]

    def test_empty_when_no_ids(self):
        assert study_phase._parse_promote_ids("no suggestions here") == []


# ---------------------------------------------------------------------------
# _parse_stale_counts
# ---------------------------------------------------------------------------

class TestParseStaleCount:
    def test_parses_both(self):
        output = "  P0 (blocking):     2\n  P1 (informational): 5\n"
        p0, p1 = study_phase._parse_stale_counts(output)
        assert p0 == 2
        assert p1 == 5

    def test_zero_on_missing(self):
        p0, p1 = study_phase._parse_stale_counts("no numbers")
        assert p0 == 0
        assert p1 == 0


# ---------------------------------------------------------------------------
# run_study — integration with stub scripts
# ---------------------------------------------------------------------------

class TestRunStudy:
    def test_all_clean_returns_empty_result(self, tmp_path):
        wiki_dir = _stub_wiki_dir(tmp_path, {
            "wiki-capture-suggest.sh": ("echo 'no candidates'", 0),
            "wiki-audit-stale.sh": ("echo 'P0 (blocking):     0\nP1 (informational): 0'", 0),
            "wiki-hot-sync.sh": ("echo 'nothing'", 0),
            "wiki-link-check.sh": ("echo 'clean'", 0),
            "promote-decision.sh": ("", 0),
            "wiki-bridge-rebuild.sh": ("", 0),
        })
        res = run_study(wiki_dir)
        assert not res.has_findings()
        assert res.summary_row() == ""

    def test_p0_blocking_on_audit_exit3(self, tmp_path):
        wiki_dir = _stub_wiki_dir(tmp_path, {
            "wiki-capture-suggest.sh": ("echo 'no candidates'", 0),
            "wiki-audit-stale.sh": (
                "echo 'P0 (blocking):     1\nP1 (informational): 0'",
                3,
            ),
            "wiki-hot-sync.sh": ("echo 'ok'", 0),
            "wiki-link-check.sh": ("echo 'clean'", 0),
            "promote-decision.sh": ("", 0),
            "wiki-bridge-rebuild.sh": ("", 0),
        })
        res = run_study(wiki_dir)
        assert res.is_p0_blocking()

    def test_p1_stale_non_blocking(self, tmp_path):
        wiki_dir = _stub_wiki_dir(tmp_path, {
            "wiki-capture-suggest.sh": ("echo 'no candidates'", 0),
            "wiki-audit-stale.sh": (
                "echo 'P0 (blocking):     0\nP1 (informational): 2'",
                2,
            ),
            "wiki-hot-sync.sh": ("echo 'ok'", 0),
            "wiki-link-check.sh": ("echo 'clean'", 0),
            "promote-decision.sh": ("", 0),
            "wiki-bridge-rebuild.sh": ("", 0),
        })
        res = run_study(wiki_dir)
        assert not res.is_p0_blocking()
        assert res.stale_p1 >= 1

    def test_link_violations_captured(self, tmp_path):
        wiki_dir = _stub_wiki_dir(tmp_path, {
            "wiki-capture-suggest.sh": ("echo 'no candidates'", 0),
            "wiki-audit-stale.sh": ("echo 'P0 (blocking):     0'", 0),
            "wiki-hot-sync.sh": ("echo 'ok'", 0),
            "wiki-link-check.sh": (
                "echo 'wikilink outside permitted dir: foo.md' >&2",
                3,
            ),
            "promote-decision.sh": ("", 0),
            "wiki-bridge-rebuild.sh": ("", 0),
        })
        res = run_study(wiki_dir)
        assert res.link_violations >= 1

    def test_hot_sync_failure_non_blocking(self, tmp_path):
        """wiki-hot-sync.sh failure must not block (ADR-0003 hot_update: always)."""
        wiki_dir = _stub_wiki_dir(tmp_path, {
            "wiki-capture-suggest.sh": ("echo 'no candidates'", 0),
            "wiki-audit-stale.sh": ("echo 'P0 (blocking):     0'", 0),
            "wiki-hot-sync.sh": ("echo 'error' >&2", 1),
            "wiki-link-check.sh": ("echo 'clean'", 0),
            "promote-decision.sh": ("", 0),
            "wiki-bridge-rebuild.sh": ("", 0),
        })
        # Must not raise; result is still usable
        res = run_study(wiki_dir)
        assert not res.is_p0_blocking()

    def test_missing_scripts_recorded_as_errors(self, tmp_path):
        """Missing scripts are logged as errors, not exceptions."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        res = run_study(wiki_dir)
        assert len(res.errors) > 0

    def test_a_step_that_did_not_run_is_not_clean(self, tmp_path):
        """Collecting an error is not the same as reporting it (#56A).

        The assertion above — `len(res.errors) > 0` — holds identically whether or not
        those errors ever reach the caller, so it constrained nothing. A step that could
        not run has verified nothing, and the result must say so.
        """
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        res = run_study(wiki_dir)
        assert res.ran_incompletely()
        assert "not-run" in res.summary_row(), res.summary_row()


# ---------------------------------------------------------------------------
# main — exit codes
# ---------------------------------------------------------------------------

class TestMainExitCodes:
    def test_absent_wiki_dir_does_not_report_clean(self, tmp_path, capsys):
        """The shipped state, asserted (#56A).

        `engine/scripts/wiki/` does not exist — the wiki scripts were extracted into a
        plugin and `/wiki:*` owns the vault now. So on a real install NONE of the six
        steps runs, yet the orchestrator printed `[study-phase] clean — no findings` and
        exited 0: a claim of health produced from the absence of any measurement.
        """
        missing = tmp_path / "no-such-wiki-dir"
        with patch.object(study_phase, "_wiki_scripts_dir", return_value=missing):
            rc = study_phase.main([])
        out = capsys.readouterr().out
        assert rc == 2, f"exit {rc} claims a health it never measured"
        assert "clean" not in out, out
        assert "not-run" in out, out

    def test_unknown_advisor_exits_1(self, monkeypatch, tmp_path):
        _make_root(tmp_path)  # populates the agents registry (kai-cto)
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
        rc = study_phase.main(["--advisor", "ghost-xyz"])
        assert rc == 1

    def test_registry_advisor_accepted(self, tmp_path, monkeypatch):
        """#47: a hired advisor outside the old VoidPay tuple is accepted."""
        root = _make_root(tmp_path)
        (root / ".claude" / "agents" / "privacy-trust.md").write_text("---\n---\n")
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
        wiki_dir = _stub_wiki_dir(tmp_path / "wiki_scripts", {
            "wiki-capture-suggest.sh": ("echo 'none'", 0),
            "wiki-audit-stale.sh": ("echo 'P0 (blocking):     0'", 0),
            "wiki-hot-sync.sh": ("echo 'ok'", 0),
            "wiki-link-check.sh": ("echo 'clean'", 0),
            "promote-decision.sh": ("", 0),
            "wiki-bridge-rebuild.sh": ("", 0),
        })
        with patch.object(study_phase, "_wiki_scripts_dir", return_value=wiki_dir):
            rc = study_phase.main(["--advisor", "privacy-trust"])
        assert rc == 0

    def test_meta_advisor_forge_accepted(self, tmp_path, monkeypatch):
        """forge is the one advisor guaranteed to exist in every instance, yet
        known_advisors() excludes META roles from roster enumeration by design.
        The gate asks a different question — "is this a valid lifecycle target" —
        so it must union the shipped meta-roles back in."""
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
        wiki_dir = _stub_wiki_dir(tmp_path / "wiki_scripts", {
            "wiki-capture-suggest.sh": ("echo 'none'", 0),
            "wiki-audit-stale.sh": ("echo 'P0 (blocking):     0'", 0),
            "wiki-hot-sync.sh": ("echo 'ok'", 0),
            "wiki-link-check.sh": ("echo 'clean'", 0),
            "promote-decision.sh": ("", 0),
            "wiki-bridge-rebuild.sh": ("", 0),
        })
        with patch.object(study_phase, "_wiki_scripts_dir", return_value=wiki_dir):
            rc = study_phase.main(["--advisor", "forge-chro"])
        assert rc == 0

    def test_p0_blocking_exits_3(self, tmp_path, monkeypatch):
        _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
        wiki_dir = _stub_wiki_dir(tmp_path / "wiki_scripts", {
            "wiki-capture-suggest.sh": ("echo 'none'", 0),
            "wiki-audit-stale.sh": ("echo 'P0 (blocking):     1'", 3),
            "wiki-hot-sync.sh": ("echo 'ok'", 0),
            "wiki-link-check.sh": ("echo 'clean'", 0),
            "promote-decision.sh": ("", 0),
            "wiki-bridge-rebuild.sh": ("", 0),
        })
        # Patch wiki scripts dir to point at our stubs
        with patch.object(study_phase, "_wiki_scripts_dir", return_value=wiki_dir):
            rc = study_phase.main(["--advisor", "kai-cto"])
        assert rc == 3

    def test_clean_exits_0(self, tmp_path, monkeypatch):
        _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
        wiki_dir = _stub_wiki_dir(tmp_path / "wiki_scripts", {
            "wiki-capture-suggest.sh": ("echo 'none'", 0),
            "wiki-audit-stale.sh": ("echo 'P0 (blocking):     0'", 0),
            "wiki-hot-sync.sh": ("echo 'ok'", 0),
            "wiki-link-check.sh": ("echo 'clean'", 0),
            "promote-decision.sh": ("", 0),
            "wiki-bridge-rebuild.sh": ("", 0),
        })
        with patch.object(study_phase, "_wiki_scripts_dir", return_value=wiki_dir):
            rc = study_phase.main(["--advisor", "kai-cto"])
        assert rc == 0
