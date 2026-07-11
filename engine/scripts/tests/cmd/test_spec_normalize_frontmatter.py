"""tests/cmd/test_spec_normalize_frontmatter.py — characterization tests for
`engine spec normalize-frontmatter`. No bats equivalent exists; these are the
canonical tests authored alongside the port.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from enginelib.spec import map_status
from tests.cmd.helpers import run_engine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_spec(specs_dir: Path, slug: str, content: str) -> Path:
    """Write ops/specs/<slug>/spec.md and return its path."""
    d = specs_dir / slug
    d.mkdir(parents=True, exist_ok=True)
    p = d / "spec.md"
    p.write_text(content)
    return p


def _specs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "ops" / "specs"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Unit tests — map_status (pure function; no subprocess needed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # canonical fast-path (no transform)
    ("proposed",    "proposed"),
    ("in-progress", "in-progress"),
    ("in-review",   "in-review"),
    ("done",        "done"),
    ("superseded",  "superseded"),
    ("abandoned",   "abandoned"),
    ("backlog",     "backlog"),
    # uppercase / mixed → canonical
    ("APPROVED",      "in-progress"),
    ("Design-Review", "in-progress"),
    ("Design-Review-Phase", "in-progress"),   # startswith prefix
    ("Ready for review", "in-review"),        # space-to-dash
    ("Completed",   "done"),
    ("MERGED",      "done"),
    ("cancelled",   "abandoned"),
    ("ready",       "in-progress"),
    ("active",      "in-progress"),
    # special
    ("",            "MISSING"),
    ("weird-value", "UNKNOWN:weird-value"),
    ("Weird Value", "UNKNOWN:Weird Value"),    # UNKNOWN preserves original raw
])
def test_map_status(raw, expected):
    assert map_status(raw) == expected


# ---------------------------------------------------------------------------
# Integration tests — engine spec normalize-frontmatter
# ---------------------------------------------------------------------------

FRONTMATTER_APPROVED = "---\nstatus: APPROVED\nspec_id: 099\n---\nBody text.\n"
FRONTMATTER_CANONICAL = "---\nstatus: in-progress\nspec_id: 099\nid: 099\n---\nBody text.\n"


def test_dry_run_leaves_file_unchanged(tmp_path, monkeypatch):
    """Dry-run prints [WOULD-CHANGE] but does NOT write the file."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    spec = _seed_spec(_specs_dir(tmp_path), "099-alpha", FRONTMATTER_APPROVED)

    r = run_engine("spec", "normalize-frontmatter")

    assert r.returncode == 0
    assert '[WOULD-CHANGE] 099-alpha: status "APPROVED" → "in-progress"' in r.stdout
    assert "Dry-run mode. Run with --apply to commit changes." in r.stdout
    # File must be unchanged
    assert spec.read_text() == FRONTMATTER_APPROVED


def test_dry_run_summary_counts(tmp_path, monkeypatch):
    """Dry-run summary shows Files reported: 0 when nothing to report."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    _seed_spec(_specs_dir(tmp_path), "099-alpha", FRONTMATTER_APPROVED)

    r = run_engine("spec", "normalize-frontmatter")

    assert "Files reported (need manual review): 0" in r.stdout


def test_apply_rewrites_status(tmp_path, monkeypatch):
    """--apply rewrites status: APPROVED → in-progress and prints [APPLIED]."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    spec = _seed_spec(_specs_dir(tmp_path), "099-alpha", FRONTMATTER_APPROVED)

    r = run_engine("spec", "normalize-frontmatter", "--apply")

    assert r.returncode == 0
    assert "[APPLIED]      099-alpha" in r.stdout
    assert "Files changed: 1" in r.stdout
    # File actually rewritten
    content = spec.read_text()
    assert "status: in-progress" in content
    assert "status: APPROVED" not in content


def test_id_alias_dry_run(tmp_path, monkeypatch):
    """Dry-run prints [WOULD-ADD] ... id: when spec_id present and id: absent."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    fm = "---\nstatus: proposed\nspec_id: 091\n---\n"
    _seed_spec(_specs_dir(tmp_path), "091-spec", fm)

    r = run_engine("spec", "normalize-frontmatter")

    assert "[WOULD-ADD]    091-spec: id: 091" in r.stdout


def test_id_alias_injected_after_spec_id(tmp_path, monkeypatch):
    """--apply injects `id: <N>` immediately after the spec_id: line."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    fm = "---\nstatus: proposed\nspec_id: 091\n---\n"
    spec = _seed_spec(_specs_dir(tmp_path), "091-spec", fm)

    r = run_engine("spec", "normalize-frontmatter", "--apply")

    assert r.returncode == 0
    lines = spec.read_text().splitlines()
    spec_id_idx = next(i for i, ln in enumerate(lines) if ln.startswith("spec_id:"))
    assert lines[spec_id_idx + 1] == "id: 091"


def test_advisor_alias_injected(tmp_path, monkeypatch):
    """--apply injects `advisor: kai-cto` after owner_suggestion: line."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    fm = "---\nstatus: proposed\nowner_suggestion: kai-cto\n---\n"
    spec = _seed_spec(_specs_dir(tmp_path), "042-spec", fm)

    r = run_engine("spec", "normalize-frontmatter", "--apply")

    assert r.returncode == 0
    content = spec.read_text()
    lines = content.splitlines()
    owner_idx = next(i for i, ln in enumerate(lines) if ln.startswith("owner_suggestion:"))
    assert lines[owner_idx + 1] == "advisor: kai-cto"
    assert "[WOULD-ADD]    042-spec: advisor: kai-cto" in r.stdout


def test_advisor_null_not_injected(tmp_path, monkeypatch):
    """owner_suggestion: null → no advisor: alias added."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    fm = "---\nstatus: proposed\nowner_suggestion: null\n---\n"
    spec = _seed_spec(_specs_dir(tmp_path), "043-spec", fm)

    r = run_engine("spec", "normalize-frontmatter", "--apply")

    assert r.returncode == 0
    content = spec.read_text()
    assert "advisor:" not in content
    assert "WOULD-ADD" not in r.stdout


def test_no_frontmatter_deferred_report(tmp_path, monkeypatch):
    """File with no leading --- produces a [NO-FRONTMATTER] deferred report."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    fm = "# Just a plain markdown file\nNo frontmatter here.\n"
    spec = _seed_spec(_specs_dir(tmp_path), "bad-spec", fm)

    r = run_engine("spec", "normalize-frontmatter")

    assert r.returncode == 0
    assert "--- Reports (no action taken) ---" in r.stdout
    assert "[NO-FRONTMATTER] bad-spec:" in r.stdout
    assert "Files reported (need manual review): 1" in r.stdout
    # File must be unchanged
    assert spec.read_text() == fm


def test_missing_status_deferred_report(tmp_path, monkeypatch):
    """Frontmatter with no status: field produces a [MISSING-STATUS] report."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    fm = "---\nspec_id: 001\ntitle: no status here\n---\n"
    _seed_spec(_specs_dir(tmp_path), "001-missing", fm)

    r = run_engine("spec", "normalize-frontmatter")

    assert "--- Reports (no action taken) ---" in r.stdout
    assert "[MISSING-STATUS] 001-missing: no status: field in frontmatter" in r.stdout
    assert "Files reported (need manual review): 1" in r.stdout


def test_unknown_status_deferred_report(tmp_path, monkeypatch):
    """An unrecognized status value produces a [UNKNOWN-STATUS] report."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    fm = "---\nstatus: weird-value\n---\n"
    _seed_spec(_specs_dir(tmp_path), "007-unknown", fm)

    r = run_engine("spec", "normalize-frontmatter")

    assert "--- Reports (no action taken) ---" in r.stdout
    assert "[UNKNOWN-STATUS] 007-unknown: status='weird-value' — not in mapping" in r.stdout
    assert "Files reported (need manual review): 1" in r.stdout


def test_idempotent(tmp_path, monkeypatch):
    """Running --apply twice: the second run produces no changes (Files changed: 0)."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    fm = "---\nstatus: APPROVED\nspec_id: 099\n---\nBody.\n"
    _seed_spec(_specs_dir(tmp_path), "099-idem", fm)

    # First apply
    r1 = run_engine("spec", "normalize-frontmatter", "--apply")
    assert r1.returncode == 0
    assert "Files changed: 1" in r1.stdout

    # Second apply — must be a no-op
    r2 = run_engine("spec", "normalize-frontmatter", "--apply")
    assert r2.returncode == 0
    assert "Files changed: 0" in r2.stdout
    assert "[WOULD-CHANGE]" not in r2.stdout
    assert "[WOULD-ADD]" not in r2.stdout
    assert "[APPLIED]" not in r2.stdout


def test_no_spec_files_exit1(tmp_path, monkeypatch):
    """No ops/specs/*/spec.md files → exit 1 with error message on stderr."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    # Do NOT create any spec files

    r = run_engine("spec", "normalize-frontmatter")

    assert r.returncode == 1
    assert "normalize-spec-frontmatter: no spec.md files found under" in r.stderr


def test_output_ordering_reports_before_summary(tmp_path, monkeypatch):
    """Reports block must appear BEFORE Summary block in stdout."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    _seed_spec(_specs_dir(tmp_path), "bad", "# no frontmatter\n")

    r = run_engine("spec", "normalize-frontmatter")

    reports_pos = r.stdout.find("--- Reports (no action taken) ---")
    summary_pos = r.stdout.find("--- Summary ---")
    assert reports_pos != -1
    assert summary_pos != -1
    assert reports_pos < summary_pos


def test_already_canonical_no_output(tmp_path, monkeypatch):
    """A fully-canonical spec with id: and advisor: already set → no inline output."""
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    fm = "---\nstatus: proposed\nspec_id: 005\nid: 005\nowner_suggestion: kai-cto\nadvisor: kai-cto\n---\n"
    _seed_spec(_specs_dir(tmp_path), "005-done", fm)

    r = run_engine("spec", "normalize-frontmatter")

    assert r.returncode == 0
    assert "[WOULD-CHANGE]" not in r.stdout
    assert "[WOULD-ADD]" not in r.stdout
    assert "Files reported (need manual review): 0" in r.stdout
