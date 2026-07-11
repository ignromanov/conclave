"""tests/cmd/test_memory_index.py — integration tests for `engine memory index`.

Ports all 7 cases from engine/scripts/tests/memory-index.bats.

Uses bare tmp_path as CONCLAVE_AI_ROOT (no canonical advisors needed — the ai_root
fixture is intentionally NOT used here).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from tests.cmd.helpers import run_engine

_NOW = "2026-04-22"


# ---------------------------------------------------------------------------
# Seed helpers (mirror _seed_decision / _seed_session / _seed_open_mention from bats)
# ---------------------------------------------------------------------------

def _seed_decision(mem_dir: Path, slug: str, date: str, by: str = "nexus-ceo") -> None:
    d = mem_dir / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{date}-{slug}.md").write_text(
        f"---\nslug: {slug}\ndate: {date}\nby: {by}\nstatus: active\n---\n\nBody.\n"
    )


def _seed_session(mem_dir: Path, advisor: str, slug: str, date: str) -> None:
    d = mem_dir / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{date}-{advisor}-{slug}.md").write_text(
        f"---\nadvisor: {advisor}\ndate: {date}\nslug: {slug}\n---\n\nOutcome.\n"
    )


def _seed_open_mention(mem_dir: Path, to: str, mention_id: str, created: str) -> None:
    d = mem_dir / "mentions" / to / "open"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{mention_id}.md").write_text(
        f"---\nid: {mention_id}\nfrom: x\nto: {to}\npriority: p2\nstatus: open\ncreated: {created}\n---\n\nBody.\n"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# 1. INDEX.md exists after run, exit 0
def test_index_creates_file(tmp_path):
    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    r = run_engine("memory", "index", "--now", _NOW, env=env)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "agent-memory" / "advisors" / "INDEX.md").is_file()


# 2. Decisions listed DESC by date
def test_decisions_sorted_desc(tmp_path):
    mem_dir = tmp_path / "agent-memory" / "advisors"
    _seed_decision(mem_dir, "older",  "2026-03-01")
    _seed_decision(mem_dir, "middle", "2026-04-10")
    _seed_decision(mem_dir, "newest", "2026-04-22")

    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    r = run_engine("memory", "index", "--now", _NOW, env=env)
    assert r.returncode == 0, r.stderr

    content = (tmp_path / "agent-memory" / "advisors" / "INDEX.md").read_text()
    lines = content.splitlines()

    # All three slugs present
    assert any("2026-04-22-newest" in ln for ln in lines)
    assert any("2026-04-10-middle" in ln for ln in lines)
    assert any("2026-03-01-older" in ln for ln in lines)

    # DESC order: newest line < middle line < older line (1-based)
    newest_line = next(i + 1 for i, ln in enumerate(lines) if "2026-04-22-newest" in ln)
    middle_line = next(i + 1 for i, ln in enumerate(lines) if "2026-04-10-middle" in ln)
    older_line  = next(i + 1 for i, ln in enumerate(lines) if "2026-03-01-older"  in ln)
    assert newest_line < middle_line < older_line


# 3. Sessions grouped by advisor
def test_sessions_grouped_by_advisor(tmp_path):
    mem_dir = tmp_path / "agent-memory" / "advisors"
    _seed_session(mem_dir, "nexus-ceo", "alpha", "2026-04-22")
    _seed_session(mem_dir, "nexus-ceo", "beta",  "2026-04-21")
    _seed_session(mem_dir, "spark-cmo", "gamma", "2026-04-20")

    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    r = run_engine("memory", "index", "--now", _NOW, env=env)
    assert r.returncode == 0, r.stderr

    content = (tmp_path / "agent-memory" / "advisors" / "INDEX.md").read_text()
    assert "nexus-ceo" in content
    assert "spark-cmo" in content
    assert "alpha" in content
    assert "beta"  in content
    assert "gamma" in content
    # ordering: advisor ASC, sessions basename-DESC within advisor (index.py two-pass sort)
    assert content.index("nexus-ceo") < content.index("spark-cmo")
    assert content.index("alpha") < content.index("beta")  # 2026-04-22 (newer) before 2026-04-21


# 4. Open mention counts per recipient
def test_open_mention_counts(tmp_path):
    mem_dir = tmp_path / "agent-memory" / "advisors"
    _seed_open_mention(mem_dir, "nexus-ceo", "2026-04-20-1030-x-to-nexus-ceo-a", "2026-04-20T10:30:00-03:00")
    _seed_open_mention(mem_dir, "nexus-ceo", "2026-04-20-1131-x-to-nexus-ceo-b", "2026-04-20T11:31:00-03:00")
    _seed_open_mention(mem_dir, "spark-cmo", "2026-04-20-1232-x-to-spark-cmo-c", "2026-04-20T12:32:00-03:00")

    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    r = run_engine("memory", "index", "--now", _NOW, env=env)
    assert r.returncode == 0, r.stderr

    import re
    content = (tmp_path / "agent-memory" / "advisors" / "INDEX.md").read_text()
    assert re.search(r"nexus-ceo.*2", content)
    assert re.search(r"spark-cmo.*1", content)


# 5. Stale mentions flagged (> 14 days old)
def test_stale_mentions_flagged(tmp_path):
    mem_dir = tmp_path / "agent-memory" / "advisors"
    # 38 days before 2026-04-22 → stale
    _seed_open_mention(mem_dir, "nexus-ceo", "2026-03-15-0900-x-to-nexus-ceo-stale", "2026-03-15T09:00:00-03:00")
    # 1 day before 2026-04-22 → fresh
    _seed_open_mention(mem_dir, "nexus-ceo", "2026-04-21-0900-x-to-nexus-ceo-fresh", "2026-04-21T09:00:00-03:00")

    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    r = run_engine("memory", "index", "--now", _NOW, env=env)
    assert r.returncode == 0, r.stderr

    content = (tmp_path / "agent-memory" / "advisors" / "INDEX.md").read_text()
    lines = content.splitlines()

    # "Stale" heading present
    stale_heading_nos = [i + 1 for i, ln in enumerate(lines) if "Stale" in ln]
    assert stale_heading_nos, "Expected a Stale section heading"
    stale_heading_line = stale_heading_nos[0]

    # Stale id appears AFTER the heading
    stale_id_nos = [i + 1 for i, ln in enumerate(lines) if "nexus-ceo-stale" in ln]
    assert stale_id_nos, "Expected stale mention id in index"
    assert stale_id_nos[0] > stale_heading_line

    # Fresh id (if present) must appear BEFORE the Stale heading
    fresh_id_nos = [i + 1 for i, ln in enumerate(lines) if "nexus-ceo-fresh" in ln]
    if fresh_id_nos:
        assert fresh_id_nos[0] < stale_heading_line


# 6. Idempotent: second run replaces, not appends
def test_idempotent(tmp_path):
    mem_dir = tmp_path / "agent-memory" / "advisors"
    _seed_decision(mem_dir, "one", "2026-04-22")

    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    index_path = tmp_path / "agent-memory" / "advisors" / "INDEX.md"

    run_engine("memory", "index", "--now", _NOW, env=env)
    first_lines = len(index_path.read_text().splitlines())

    run_engine("memory", "index", "--now", _NOW, env=env)
    second_lines = len(index_path.read_text().splitlines())

    assert first_lines == second_lines


# 7. Does NOT commit — INDEX.md remains untracked after run
def test_does_not_commit(tmp_path):
    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}

    # Establish a clean git baseline (empty repo)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@test.com", "-c", "user.name=Test",
         "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=tmp_path, check=True,
    )

    r = run_engine("memory", "index", "--now", _NOW, env=env)
    assert r.returncode == 0, r.stderr

    result = subprocess.run(
        ["git", "status", "--short"], cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    assert len(result.stdout.strip()) > 0, "expected untracked INDEX.md; git shows clean"
