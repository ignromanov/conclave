"""tests/cmd/test_lifecycle_git_fetch.py — integration tests for `engine lifecycle git-fetch`.

Hermetic: bare tmp_path (NOT ai_root). Uses CONCLAVE_AI_ROOT seam for isolation.
Port of engine/scripts/tests/lifecycle/git-fetch.bats (5 cases).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tests.cmd.helpers import make_git_repo, run_engine


def _cache_path(tmp: Path) -> Path:
    return tmp / "agent-memory" / "git-cache" / "state.md"


def _run_log_path(tmp: Path) -> Path:
    today = datetime.now(UTC).date().isoformat()
    return tmp / "agent-memory" / "run-log" / f"{today}.jsonl"


def _env(tmp: Path) -> dict:
    return {"CONCLAVE_AI_ROOT": str(tmp), "SNAPSHOT_GIT_TTL": "60"}


_FRESH_BODY = (
    '---\ntype: git-snapshot\nschema_version: 1\ntags: [op/git-snapshot]\n'
    'advisor: shared\ncaptured_at: "2026-06-27T00:00:00Z"\nttl_seconds: 60\n'
    'branch: master\nworktree: main\n---\n\n# Git Snapshot\n\n'
    '- Branch: master\n- Worktree: main\n- Status: clean\n\n'
    'Content padding to exceed 100 bytes minimum size threshold requirement.\n'
)


# ---------------------------------------------------------------------------
# 1. No cache → exit 2, writes state.md with valid frontmatter.
# ---------------------------------------------------------------------------
def test_no_cache_writes_state_and_exits_2(tmp_path):
    cache = _cache_path(tmp_path)
    assert not cache.parent.exists()

    r = run_engine("lifecycle", "git-fetch", env=_env(tmp_path))
    assert r.returncode == 2
    assert cache.exists()
    text = cache.read_text(encoding="utf-8")
    assert "type: git-snapshot" in text
    assert "schema_version: 1" in text
    assert "branch:" in text


# ---------------------------------------------------------------------------
# 2. Fresh cache → exit 0 (cache hit, no re-fetch).
# ---------------------------------------------------------------------------
def test_fresh_cache_returns_hit(tmp_path):
    cache = _cache_path(tmp_path)
    cache.parent.mkdir(parents=True, exist_ok=True)
    assert len(_FRESH_BODY.encode()) >= 100, "fixture body must be >= 100 bytes"
    cache.write_text(_FRESH_BODY, encoding="utf-8")

    r = run_engine("lifecycle", "git-fetch", env=_env(tmp_path))
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# 3. --no-cache → exit 2 (force re-fetch even with fresh cache).
# ---------------------------------------------------------------------------
def test_no_cache_flag_forces_refetch(tmp_path):
    cache = _cache_path(tmp_path)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(_FRESH_BODY, encoding="utf-8")

    r = run_engine("lifecycle", "git-fetch", "--no-cache", env=_env(tmp_path))
    assert r.returncode == 2


# ---------------------------------------------------------------------------
# 4. Run-log row appended; script name is "engine lifecycle git-fetch".
# ---------------------------------------------------------------------------
def test_run_log_row_script_name(tmp_path):
    r = run_engine("lifecycle", "git-fetch", env=_env(tmp_path))
    assert r.returncode == 2

    log = _run_log_path(tmp_path)
    assert log.exists()
    rows = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(row.get("script") == "engine lifecycle git-fetch" for row in rows), (
        f"expected script='engine lifecycle git-fetch' in run-log; got: {rows}"
    )


# ---------------------------------------------------------------------------
# 4b. The snapshot describes the CONSUMER's repository, never the engine checkout.
#
#     `run_engine` defaults its cwd to engine/scripts — exactly what session_init does —
#     and unpinned, `git status` / `git worktree list` / `git symbolic-ref` all inherited it.
#     So every consumer's DATA tree recorded the ENGINE's branch and the maintainer's
#     absolute worktree paths. Note that test 1 above cannot catch this: `"branch:" in text`
#     holds whichever repository git read.
# ---------------------------------------------------------------------------
def test_snapshot_reads_the_consumer_repo_not_the_process_cwd(tmp_path):
    consumer = make_git_repo(tmp_path / "consumer", branch="consumer-side-branch")

    r = run_engine(
        "lifecycle", "git-fetch", "--no-cache",
        env={**_env(tmp_path), "CONCLAVE_GIT_REMOTE_CWD": str(consumer)},
    )
    assert r.returncode == 2, r.stderr

    text = _cache_path(tmp_path).read_text(encoding="utf-8")
    assert "branch: consumer-side-branch" in text, (
        f"snapshot names a branch the consumer repo does not have:\n{text}"
    )
    # The worktree table is where the maintainer's filesystem layout leaked. It must name the
    # consumer's checkout and nothing above it.
    assert str(consumer.resolve()) in text, f"consumer worktree missing from table:\n{text}"
    engine_checkout = Path(__file__).resolve().parents[3]  # …/engine/scripts/tests/cmd -> repo
    assert str(engine_checkout) not in text, (
        f"the engine checkout path leaked into the consumer's snapshot:\n{text}"
    )


# ---------------------------------------------------------------------------
# 5. TRIPWIRE marker present in enginelib/lifecycle/git_fetch.py source.
# ---------------------------------------------------------------------------
def test_tripwire_marker_in_source():
    # engine/scripts/tests/cmd/test_lifecycle_git_fetch.py
    # parents: [0]=cmd  [1]=tests  [2]=scripts
    module = Path(__file__).resolve().parents[2] / "enginelib" / "lifecycle" / "git_fetch.py"
    assert module.exists(), f"module not found: {module}"
    assert "# TRIPWIRE" in module.read_text(encoding="utf-8")
