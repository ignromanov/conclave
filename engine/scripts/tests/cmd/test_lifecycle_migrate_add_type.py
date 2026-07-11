"""tests/cmd/test_lifecycle_migrate_add_type.py — integration tests for `engine lifecycle migrate-add-type`.

Hermetic: bare tmp_path (NOT ai_root). Uses CONCLAVE_AI_ROOT seam for run-log isolation.
Port of engine/scripts/tests/lifecycle/migrate-add-type.bats (8 cases).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from tests.cmd.helpers import run_engine

# ---------------------------------------------------------------------------
# Inline fixtures (match brief spec exactly)
# ---------------------------------------------------------------------------
PARTIAL = "---\nschema_version: 1\n---\n\nbody\n"
ALREADY_TYPED = "---\ntype: audit-finding\n---\n\nbody\n"
NO_FRONTMATTER = "just body text\n"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. Injects type=decision for file under decisions/
# ---------------------------------------------------------------------------
def test_injects_decision(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "decisions" / "foo.md", PARTIAL)

    r = run_engine("lifecycle", "migrate-add-type", "--root", str(root))
    assert r.returncode == 0
    assert re.search(r"^type: decision$", f.read_text(encoding="utf-8"), re.M)


# ---------------------------------------------------------------------------
# 2. Skips file already typed — byte-identical
# ---------------------------------------------------------------------------
def test_already_typed_unchanged(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "audit" / "already.md", ALREADY_TYPED)
    before = f.read_text(encoding="utf-8")

    r = run_engine("lifecycle", "migrate-add-type", "--root", str(root))
    assert r.returncode == 0
    assert f.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# 3. Creates frontmatter block when file has no frontmatter
# ---------------------------------------------------------------------------
def test_no_frontmatter_creates_block(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "sessions" / "bare.md", NO_FRONTMATTER)

    r = run_engine("lifecycle", "migrate-add-type", "--root", str(root))
    assert r.returncode == 0

    content = f.read_text(encoding="utf-8")
    assert content.splitlines()[0] == "---"
    assert re.search(r"^type: session$", content, re.M)


# ---------------------------------------------------------------------------
# 4. --dry-run reports WOULD INJECT without mutating
# ---------------------------------------------------------------------------
def test_dry_run(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "decisions" / "foo.md", PARTIAL)
    before = f.read_text(encoding="utf-8")

    r = run_engine("lifecycle", "migrate-add-type", "--root", str(root), "--dry-run")
    assert r.returncode == 0
    assert "WOULD INJECT" in r.stdout
    assert "decision" in r.stdout
    assert f.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# 5. Unknown path → skip with warning, exit 0, file unchanged
# ---------------------------------------------------------------------------
def test_unknown_path_skipped(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "orphans" / "foo.md", PARTIAL)
    before = f.read_text(encoding="utf-8")

    r = run_engine("lifecycle", "migrate-add-type", "--root", str(root))
    assert r.returncode == 0
    assert f.read_text(encoding="utf-8") == before
    combined = r.stdout + r.stderr
    assert "skip" in combined or "unknown" in combined


# ---------------------------------------------------------------------------
# 6. Idempotent — second run leaves files byte-identical to after first run
# ---------------------------------------------------------------------------
def test_idempotent(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "decisions" / "foo.md", PARTIAL)

    r1 = run_engine("lifecycle", "migrate-add-type", "--root", str(root))
    assert r1.returncode == 0
    after_first = f.read_text(encoding="utf-8")

    r2 = run_engine("lifecycle", "migrate-add-type", "--root", str(root))
    assert r2.returncode == 0
    assert f.read_text(encoding="utf-8") == after_first


# ---------------------------------------------------------------------------
# 7. Run-log row injected=N,skipped=M (exercises dispatcher run-log args hook)
# ---------------------------------------------------------------------------
def test_run_log_injected_skipped(tmp_path):
    root = tmp_path / "tree"
    _write(root / "decisions" / "foo.md", PARTIAL)
    _write(root / "orphans" / "bar.md", PARTIAL)

    today = datetime.now(UTC).date().isoformat()
    log_path = tmp_path / "agent-memory" / "run-log" / f"{today}.jsonl"
    before_lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []

    r = run_engine(
        "lifecycle", "migrate-add-type", "--root", str(root),
        env={"CONCLAVE_AI_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0

    assert log_path.exists()
    after_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(after_lines) > len(before_lines)

    new_lines = after_lines[len(before_lines):]
    assert any(
        "injected=" in line and "skipped=" in line and "engine lifecycle migrate-add-type" in line
        for line in new_lines
    )


# ---------------------------------------------------------------------------
# 8. Multiple path mappings each get correct type
# ---------------------------------------------------------------------------
def test_multiple_mappings(tmp_path):
    root = tmp_path / "tree"
    d = _write(root / "decisions" / "d.md", PARTIAL)
    s = _write(root / "sessions" / "s.md", PARTIAL)
    m = _write(root / "mentions" / "kai-cto" / "m.md", PARTIAL)
    a = _write(root / "audit" / "a.md", PARTIAL)

    r = run_engine("lifecycle", "migrate-add-type", "--root", str(root))
    assert r.returncode == 0

    assert re.search(r"^type: decision$",     d.read_text(encoding="utf-8"), re.M)
    assert re.search(r"^type: session$",      s.read_text(encoding="utf-8"), re.M)
    assert re.search(r"^type: mention$",      m.read_text(encoding="utf-8"), re.M)
    assert re.search(r"^type: audit-finding$", a.read_text(encoding="utf-8"), re.M)
