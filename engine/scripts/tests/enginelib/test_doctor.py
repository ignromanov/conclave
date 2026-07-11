"""tests/enginelib/test_doctor.py — #49(c) First-Launch preflight.

Hermetic: operates on tmp roots only.
"""
from __future__ import annotations

from enginelib import doctor


def _mk_root(tmp_path):
    (tmp_path / "agent-memory").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _check(checks, name):
    return next(c for c in checks if c.name == name)


def test_missing_hot_reported_not_ok(tmp_path):
    root = _mk_root(tmp_path)
    checks = doctor.run_checks(root)
    assert _check(checks, "hot.md").ok is False
    assert doctor.exit_code(checks) != 0


def test_fix_seeds_hot_skeleton(tmp_path):
    root = _mk_root(tmp_path)
    checks = doctor.run_checks(root, fix=True)
    hot = root / "agent-memory" / "hot.md"
    assert hot.is_file()
    text = hot.read_text(encoding="utf-8")
    for header in ("## Now", "## Recent decisions", "## Watch"):
        assert header in text
    assert _check(checks, "hot.md").ok is True


def test_wellformed_hot_is_ok(tmp_path):
    root = _mk_root(tmp_path)
    (root / "agent-memory" / "hot.md").write_text(
        "## Now\n\n## Open threads\n\n## Recent decisions\n\n## Watch\n", encoding="utf-8"
    )
    checks = doctor.run_checks(root)
    assert _check(checks, "hot.md").ok is True


def test_malformed_hot_flagged_and_not_clobbered_without_fix(tmp_path):
    root = _mk_root(tmp_path)
    hot = root / "agent-memory" / "hot.md"
    hot.write_text("garbage no sections here\n", encoding="utf-8")
    checks = doctor.run_checks(root)
    assert _check(checks, "hot.md").ok is False
    # Content preserved (never silently overwritten without --fix).
    assert hot.read_text(encoding="utf-8") == "garbage no sections here\n"


def test_advisor_in_registry_ok(tmp_path):
    root = _mk_root(tmp_path)
    (root / ".claude" / "agents" / "sage-cto.md").write_text("# advisor\n", encoding="utf-8")
    checks = doctor.run_checks(root, advisor="sage-cto")
    assert _check(checks, "advisor:sage-cto").ok is True


def test_advisor_not_in_registry_flagged(tmp_path):
    root = _mk_root(tmp_path)
    checks = doctor.run_checks(root, advisor="ghost")
    assert _check(checks, "advisor:ghost").ok is False
    assert doctor.exit_code(checks) != 0


def test_forge_meta_advisor_accepted(tmp_path):
    root = _mk_root(tmp_path)
    checks = doctor.run_checks(root, advisor="forge")
    assert _check(checks, "advisor:forge").ok is True
