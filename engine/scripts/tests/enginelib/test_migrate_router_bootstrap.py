"""Migrating the bootstrap fence in routers that are already minted.

`render_router` refuses to overwrite an enriched wrapper (#58) — correctly, since hire-time
identity and the `forge:` block live there and a blind re-render wipes them. The consequence is
that the bash fence, which is engine-owned and arrives from the template, freezes at mint time:
a fix to the template reaches new instances and no existing one. That is why the
`${CLAUDE_PLUGIN_ROOT:-.}` bootstrap survived eleven reports — every deployed router carries its
own private copy.

This migration splits the wrapper by ownership: the fence is refreshed from the template, and
everything else in the file is left exactly as the instance wrote it.
"""
from __future__ import annotations

import pytest

from enginelib import paths  # noqa: F401  (import-time check that the package resolves)
from enginelib.lifecycle import migrate_router_bootstrap

STALE_FENCE = (
    "```bash\n"
    'ROOT="${CLAUDE_PLUGIN_ROOT:-.}"   # installed plugin → plugin dir\n'
    'PYTHONPATH="$ROOT/engine/scripts" python3 '
    '"$ROOT/engine/scripts/lifecycle/session_init.py" --advisor vera-cto\n'
    "```"
)

ENRICHED_ROUTER = f"""---
name: conclave-vera-cto
description: >-
  🔬 Vera — Engineering advisor. Hand-written at hire time.
forge:
  model-version: 1.4.0
  hired-by: forge-chro
---

You are being invoked as **Vera** 🔬, the **vera-cto** advisor.

{STALE_FENCE}

Then follow the full `/conclave:start` protocol as advisor `vera-cto`.
"""


def _seed_template(tmp_path, monkeypatch):
    """A real template tree, sibling of engine/ — the layout templates_dir() resolves."""
    engine = tmp_path / "engine"
    engine.mkdir(exist_ok=True)
    tdir = tmp_path / "skills" / "forge-operations" / "references" / "templates"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "advisor-router.md").write_text(
        "---\nname: conclave-${ID}\n---\n\n"
        "You are being invoked as the **${ID}** advisor.\n\n"
        "```bash\n"
        'ROOT="${CONCLAVE_ENGINE_ROOT:-${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/engine}}"\n'
        'PYTHONPATH="$ROOT/scripts" python3 '
        '"$ROOT/scripts/lifecycle/session_init.py" --advisor ${ID}\n'
        "```\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine))


def _seed_router(skills_root, body=ENRICHED_ROUTER, advisor="vera-cto"):
    d = skills_root / f"conclave-{advisor}"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_refreshes_a_stale_fence_in_an_enriched_router(tmp_path, monkeypatch):
    """The fence is replaced by the template's; nothing else in the file moves."""
    _seed_template(tmp_path, monkeypatch)
    skills_root = tmp_path / ".claude" / "skills"
    router_file = _seed_router(skills_root)

    result = migrate_router_bootstrap.run(skills_root)

    body = router_file.read_text(encoding="utf-8")
    assert result.updated == 1
    assert "CLAUDE_PLUGIN_ROOT:-." not in body, "the stale bootstrap survived the migration"
    assert '"$ROOT/scripts/lifecycle/session_init.py" --advisor vera-cto' in body
    # enrichment is instance-owned and must be untouched
    assert "🔬 Vera — Engineering advisor. Hand-written at hire time." in body
    assert "model-version: 1.4.0" in body
    assert "Then follow the full `/conclave:start` protocol" in body


def test_is_idempotent(tmp_path, monkeypatch):
    """A second run reports nothing to do — the migration is safe to re-run."""
    _seed_template(tmp_path, monkeypatch)
    skills_root = tmp_path / ".claude" / "skills"
    _seed_router(skills_root)

    migrate_router_bootstrap.run(skills_root)
    second = migrate_router_bootstrap.run(skills_root)

    assert second.updated == 0
    assert second.skipped == 1


def test_dry_run_reports_without_writing(tmp_path, monkeypatch):
    """dry_run names what would change and writes nothing (the migrate-* contract)."""
    _seed_template(tmp_path, monkeypatch)
    skills_root = tmp_path / ".claude" / "skills"
    router_file = _seed_router(skills_root)
    before = router_file.read_text(encoding="utf-8")

    result = migrate_router_bootstrap.run(skills_root, dry_run=True)

    assert result.updated == 0
    assert [p.split("/")[-2] for p in result.would_update] == ["conclave-vera-cto"]
    assert router_file.read_text(encoding="utf-8") == before


def test_a_router_with_no_bootstrap_fence_is_skipped_not_rewritten(tmp_path, monkeypatch):
    """Absence of the fence is not a defect to repair — the migration only refreshes."""
    _seed_template(tmp_path, monkeypatch)
    skills_root = tmp_path / ".claude" / "skills"
    router_file = _seed_router(skills_root, body="---\nname: conclave-vera-cto\n---\n\nprose only\n")

    result = migrate_router_bootstrap.run(skills_root)

    assert result.updated == 0
    assert result.skipped == 1
    assert router_file.read_text(encoding="utf-8") == "---\nname: conclave-vera-cto\n---\n\nprose only\n"


def test_a_template_without_exactly_one_bootstrap_fence_raises(tmp_path, monkeypatch):
    """The migration installs the template's fence; two candidates means it cannot know which."""
    _seed_template(tmp_path, monkeypatch)
    tdir = tmp_path / "skills" / "forge-operations" / "references" / "templates"
    t = tdir / "advisor-router.md"
    t.write_text(t.read_text(encoding="utf-8") * 2, encoding="utf-8")
    skills_root = tmp_path / ".claude" / "skills"
    _seed_router(skills_root)

    with pytest.raises(RuntimeError, match="advisor-router.md"):
        migrate_router_bootstrap.run(skills_root)
