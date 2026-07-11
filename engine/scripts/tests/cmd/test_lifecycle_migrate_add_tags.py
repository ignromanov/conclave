"""tests/cmd/test_lifecycle_migrate_add_tags.py — integration tests for `engine lifecycle migrate-add-tags`.

Hermetic: bare tmp_path (NOT ai_root). Uses CONCLAVE_AI_ROOT seam for run-log isolation.
Port of engine/scripts/tests/lifecycle/migrate-add-tags.bats (7 cases).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from tests.cmd.helpers import run_engine

# ---------------------------------------------------------------------------
# Inline fixtures (match brief spec exactly)
# ---------------------------------------------------------------------------

def _typed(t: str) -> str:
    return f"---\ntype: {t}\nschema_version: 1\nid: test-id\n---\n\n# body\n"


def _typed_tagged(t: str) -> str:
    return f"---\ntype: {t}\nschema_version: 1\ntags: [op/{t}, status/open]\nid: test-id\n---\n\n# body\n"


PARTIAL = "---\nschema_version: 1\n---\n\nbody\n"
NO_FRONTMATTER = "just body text\n"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. Injects tags=[op/decision] for file with type: decision
# ---------------------------------------------------------------------------
def test_injects_tags_for_decision(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "decisions" / "foo.md", _typed("decision"))

    r = run_engine("lifecycle", "migrate-add-tags", "--root", str(root))
    assert r.returncode == 0
    assert re.search(r"^tags: \[op/decision\]$", f.read_text(encoding="utf-8"), re.M)


# ---------------------------------------------------------------------------
# 2. Skips file already tagged — byte-identical
# ---------------------------------------------------------------------------
def test_already_tagged_unchanged(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "sessions" / "bar.md", _typed_tagged("session"))
    before = f.read_text(encoding="utf-8")

    r = run_engine("lifecycle", "migrate-add-tags", "--root", str(root))
    assert r.returncode == 0
    assert f.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# 3. Skips file without type: — warning emitted, exit 0, file unchanged
# ---------------------------------------------------------------------------
def test_no_type_skipped(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "decisions" / "untyped.md", PARTIAL)
    before = f.read_text(encoding="utf-8")

    r = run_engine("lifecycle", "migrate-add-tags", "--root", str(root))
    assert r.returncode == 0
    assert f.read_text(encoding="utf-8") == before

    combined = r.stdout + r.stderr
    assert "skip" in combined or "type" in combined or "SKIP" in combined


# ---------------------------------------------------------------------------
# 4. --dry-run reports WOULD INJECT without mutating
# ---------------------------------------------------------------------------
def test_dry_run(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "decisions" / "foo.md", _typed("decision"))
    before = f.read_text(encoding="utf-8")

    r = run_engine("lifecycle", "migrate-add-tags", "--root", str(root), "--dry-run")
    assert r.returncode == 0
    assert "WOULD INJECT" in r.stdout
    assert "op/decision" in r.stdout
    assert f.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# 5. Idempotent — second run leaves files byte-identical to after first run
# ---------------------------------------------------------------------------
def test_idempotent(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "decisions" / "foo.md", _typed("decision"))

    r1 = run_engine("lifecycle", "migrate-add-tags", "--root", str(root))
    assert r1.returncode == 0
    after_first = f.read_text(encoding="utf-8")

    r2 = run_engine("lifecycle", "migrate-add-tags", "--root", str(root))
    assert r2.returncode == 0
    assert f.read_text(encoding="utf-8") == after_first


# ---------------------------------------------------------------------------
# 6. Run-log row appended with injected= and script name
# ---------------------------------------------------------------------------
def test_run_log_injected(tmp_path):
    root = tmp_path / "tree"
    _write(root / "decisions" / "foo.md", _typed("decision"))

    today = datetime.now(UTC).date().isoformat()
    log_path = tmp_path / "agent-memory" / "run-log" / f"{today}.jsonl"
    before_lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []

    r = run_engine(
        "lifecycle", "migrate-add-tags", "--root", str(root),
        env={"CONCLAVE_AI_ROOT": str(tmp_path)},
    )
    assert r.returncode == 0

    assert log_path.exists()
    after_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(after_lines) > len(before_lines)

    new_lines = after_lines[len(before_lines):]
    assert any(
        "injected=" in line and "engine lifecycle migrate-add-tags" in line
        for line in new_lines
    )


# ---------------------------------------------------------------------------
# 7. Combined: bare file → type: via migrate-add-type, then tags: via migrate-add-tags
# ---------------------------------------------------------------------------
def test_combined_add_type_then_add_tags(tmp_path):
    root = tmp_path / "tree"
    f = _write(root / "decisions" / "bare.md", NO_FRONTMATTER)

    # Step 1: inject type:
    r1 = run_engine("lifecycle", "migrate-add-type", "--root", str(root))
    assert r1.returncode == 0
    assert re.search(r"^type: decision$", f.read_text(encoding="utf-8"), re.M)

    # Step 2: inject tags:
    r2 = run_engine("lifecycle", "migrate-add-tags", "--root", str(root))
    assert r2.returncode == 0
    assert re.search(r"^tags: \[op/decision\]$", f.read_text(encoding="utf-8"), re.M)
