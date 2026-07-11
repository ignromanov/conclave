"""tests/cmd/test_overlay_apply.py — integration tests for `engine overlay apply`.

Ports engine/scripts/tests/apply-overlay.test.sh (usage case) and extends with
8 cases covering the full action matrix.

Hermeticity: uses ai_root fixture (CONCLAVE_AI_ROOT + CONCLAVE_ENGINE_ROOT set via
monkeypatch → inherited by run_engine subprocess). Base contracts are seeded at
contracts_dir() = engine_root()/contracts/<name>.md.
"""
from __future__ import annotations

import os
from pathlib import Path

from tests.cmd.helpers import run_engine


def _contracts_dir(ai_root) -> Path:
    """contracts_dir() = CONCLAVE_ENGINE_ROOT/contracts."""
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    d = engine_root / "contracts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _seed_base(ai_root, name: str = "foo", version: str = "1.2.3") -> Path:
    """Seed a base contract file with a version: line."""
    contracts = _contracts_dir(ai_root)
    base = contracts / f"{name}.md"
    base.write_text(f"version: {version}\n# {name} contract\n", encoding="utf-8")
    return base


def _overlay_path(ai_root, advisor: str, contract: str) -> Path:
    """Expected overlay path under repo_root (= CONCLAVE_AI_ROOT). The ai_root fixture
    pre-seeds legacy team.<id> dirs for the canonical roster, so #54 dual-read resolves
    kai-cto to its existing team.<id> dir (see test_fresh_advisor_lands_conclave for the
    conclave-<id> default on an unseeded id)."""
    return ai_root / ".claude" / "skills" / f"team.{advisor}" / "contracts" / f"{contract}.md"


# ---------------------------------------------------------------------------
# 1. No args → exit 1 + "usage" in stderr  (ports apply-overlay.test.sh)
# ---------------------------------------------------------------------------
def test_no_args_usage(ai_root):
    r = run_engine("overlay", "apply")
    assert r.returncode == 1
    assert "usage" in r.stderr


# ---------------------------------------------------------------------------
# 2. add happy path
# ---------------------------------------------------------------------------
def test_add_happy_path(ai_root):
    _seed_base(ai_root, "foo", "1.2.3")

    r = run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "foo",
        "--type", "constraint",
        "--action", "add",
    )
    assert r.returncode == 0, r.stderr

    overlay = _overlay_path(ai_root, "kai-cto", "foo")
    assert overlay.exists(), "overlay file was not created"

    # stdout
    assert "created:" in r.stdout
    assert str(overlay) in r.stdout

    # file content assertions
    content = overlay.read_text(encoding="utf-8")
    assert "overrides-base-version: 1.2.3" in content
    assert "type: constraint" in content
    assert "## Constraint: <short title>" in content
    assert "# team.kai-cto overlay: foo" in content  # dual-read: fixture pre-seeds team.kai-cto
    assert "advisor: kai-cto" in content
    assert "contract: foo" in content


# ---------------------------------------------------------------------------
# 2b. #54: a FRESH advisor (no pre-existing SKILL dir) lands on the canonical
# conclave-<id> prefix, and the overlay body names that dir.
# ---------------------------------------------------------------------------
def test_fresh_advisor_lands_conclave(ai_root):
    _seed_base(ai_root, "foo", "1.2.3")
    advisor = "newbie-cto"  # not in the auto-seeded canonical roster

    r = run_engine(
        "overlay", "apply",
        "--advisor", advisor,
        "--contract", "foo",
        "--type", "constraint",
        "--action", "add",
    )
    assert r.returncode == 0, r.stderr

    landed = ai_root / ".claude" / "skills" / f"conclave-{advisor}" / "contracts" / "foo.md"
    assert landed.exists(), "fresh advisor overlay should land on the canonical conclave- prefix"
    assert f"# conclave-{advisor} overlay: foo" in landed.read_text(encoding="utf-8")
    assert not (ai_root / ".claude" / "skills" / f"team.{advisor}").exists()


# ---------------------------------------------------------------------------
# 3. add when overlay already exists → exit 3 + "overlay already exists" in stderr
# ---------------------------------------------------------------------------
def test_add_overlay_exists(ai_root):
    _seed_base(ai_root, "foo")

    # First add succeeds.
    r1 = run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "foo",
        "--type", "constraint",
        "--action", "add",
    )
    assert r1.returncode == 0, r1.stderr

    # Second add → conflict.
    r2 = run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "foo",
        "--type", "constraint",
        "--action", "add",
    )
    assert r2.returncode == 3
    assert "overlay already exists" in r2.stderr


# ---------------------------------------------------------------------------
# 4. base contract missing → exit 2 + "base contract missing" in stderr
# ---------------------------------------------------------------------------
def test_base_missing(ai_root):
    # No base seeded for "nonexistent".
    r = run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "nonexistent",
        "--type", "constraint",
        "--action", "add",
    )
    assert r.returncode == 2
    assert "base contract missing" in r.stderr


# ---------------------------------------------------------------------------
# 5. remove existing overlay → exit 0, stdout "removed: …", file gone
# ---------------------------------------------------------------------------
def test_remove_existing(ai_root):
    _seed_base(ai_root, "foo")

    # Create the overlay first.
    run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "foo",
        "--type", "constraint",
        "--action", "add",
    )
    overlay = _overlay_path(ai_root, "kai-cto", "foo")
    assert overlay.exists()

    r = run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "foo",
        "--action", "remove",
    )
    assert r.returncode == 0, r.stderr
    assert "removed:" in r.stdout
    assert str(overlay) in r.stdout
    assert not overlay.exists(), "overlay file should be deleted"


# ---------------------------------------------------------------------------
# 6. remove non-existent overlay → exit 0 + "no overlay to remove" in stderr
# ---------------------------------------------------------------------------
def test_remove_nonexistent(ai_root):
    _seed_base(ai_root, "foo")

    r = run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "foo",
        "--action", "remove",
    )
    assert r.returncode == 0
    assert "no overlay to remove" in r.stderr


# ---------------------------------------------------------------------------
# 7. modify non-existent overlay → exit 3 + "no overlay to modify" in stderr
# ---------------------------------------------------------------------------
def test_modify_nonexistent(ai_root):
    _seed_base(ai_root, "foo")

    r = run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "foo",
        "--action", "modify",
    )
    assert r.returncode == 3
    assert "no overlay to modify" in r.stderr


# ---------------------------------------------------------------------------
# 8. modify existing overlay → exit 0 + "modify in editor" in stdout
# ---------------------------------------------------------------------------
def test_modify_existing(ai_root):
    _seed_base(ai_root, "foo")

    # Create overlay first.
    run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "foo",
        "--type", "constraint",
        "--action", "add",
    )
    overlay = _overlay_path(ai_root, "kai-cto", "foo")
    assert overlay.exists()
    before = overlay.read_bytes()

    r = run_engine(
        "overlay", "apply",
        "--advisor", "kai-cto",
        "--contract", "foo",
        "--action", "modify",
    )
    assert r.returncode == 0, r.stderr
    assert "modify in editor:" in r.stdout
    assert str(overlay) in r.stdout
    # File must be unchanged (modify is no-op) — byte-for-byte, not just present.
    assert overlay.exists()
    assert overlay.read_bytes() == before
