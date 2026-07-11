"""tests/cmd/test_audit_specs_registry.py — integration tests for `engine audit specs-registry`."""
from tests.cmd.helpers import run_engine


def test_clean_registry(tmp_path, monkeypatch):
    specs = tmp_path / "ops" / "specs"
    (specs / "001-alpha").mkdir(parents=True)
    (specs / "001-alpha" / "spec.md").write_text("x")
    (specs / "REGISTRY.md").write_text("[alpha](001-alpha/spec.md)\n")
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = run_engine("audit", "specs-registry")
    assert r.returncode == 0
    assert "0 CRIT" in r.stdout


def test_collision_is_crit(tmp_path, monkeypatch):
    specs = tmp_path / "ops" / "specs"
    for slug in ("001-alpha", "001-beta"):
        (specs / slug).mkdir(parents=True)
        (specs / slug / "spec.md").write_text("x")
    (specs / "REGISTRY.md").write_text("[a](001-alpha/) [b](001-beta/)\n")
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = run_engine("audit", "specs-registry")
    assert r.returncode == 1
    assert "collision 001" in r.stdout


def test_empty_specs_dir_is_clean(tmp_path, monkeypatch):
    """R6's intent, preserved: a fresh instance has no specs and needs no REGISTRY."""
    (tmp_path / "ops" / "specs").mkdir(parents=True)   # no specs, no REGISTRY.md
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = run_engine("audit", "specs-registry")
    assert r.returncode == 0


def test_specs_present_without_registry_is_crit(tmp_path, monkeypatch):
    """R6's overreach, corrected: specs that exist but cannot be traced are not 'clean'.

    A gate that reports 0 CRIT because it is unable to run has not verified anything.
    """
    specs = tmp_path / "ops" / "specs"
    (specs / "001-alpha").mkdir(parents=True)
    (specs / "001-alpha" / "spec.md").write_text("x")
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = run_engine("audit", "specs-registry")
    assert r.returncode == 1
    assert "REGISTRY.md absent" in r.stdout


def test_flat_md_specs_are_not_invisible(tmp_path, monkeypatch):
    """The live tree stores specs as flat NNN-slug.md, not NNN-slug/ dirs.

    The dir-only scan saw zero specs and passed vacuously on a non-empty tree.
    """
    specs = tmp_path / "ops" / "specs"
    specs.mkdir(parents=True)
    (specs / "102-engine-web-dashboard-v2.md").write_text("x")
    (specs / "103-two-repo-code-data-split.md").write_text("x")
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = run_engine("audit", "specs-registry")
    assert r.returncode == 1, "two untraced flat specs must not report clean"


def test_absent_specs_dir_is_crit(tmp_path, monkeypatch):
    """The gate's target moved/renamed — fail loudly, per test_gates.py's scanned>0 rule."""
    (tmp_path / "ops").mkdir(parents=True)             # no specs/ at all
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = run_engine("audit", "specs-registry")
    assert r.returncode == 1
    assert "specs dir absent" in r.stdout
