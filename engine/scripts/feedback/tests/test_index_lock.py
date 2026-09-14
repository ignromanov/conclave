"""test_index_lock.py — 118 C1.1: the index write path is serialized and atomic.

Three defects this file pins, each named in the spec rather than inferred:

1. `feedback_index.py` wrote a FIXED `index.tmp`. Two concurrent rebuilds wrote the
   same temporary file and `os.replace` then published a half-written one as valid.
2. It took no lock at all, while triage/verify took `.triage-lock`. The lock existed;
   it was not the lock the other writer (the post-commit hook) took.
3. It saw corruption and threw it away — `except json.JSONDecodeError: pass`.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from briefing.frontmatter_io import write

SCRIPTS_DIR = Path(__file__).parent.parent.parent
FEEDBACK_PKG = Path(__file__).parent.parent

sys.path.insert(0, str(SCRIPTS_DIR))
from enginelib.lock import lock_path_for, with_lock  # noqa: E402
from feedback.paths import index_lock_target  # noqa: E402


def _env(root: Path, lock_dir: Path) -> dict:
    return {
        "PYTHONPATH": str(SCRIPTS_DIR),
        "CONCLAVE_AI_ROOT": str(root),
        "LOCK_DIR": str(lock_dir),
        "PATH": "/usr/bin:/bin",
    }


def _run_index(root: Path, lock_dir: Path, extra: list[str] | None = None,
               env_extra: dict | None = None):
    env = _env(root, lock_dir)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(FEEDBACK_PKG / "feedback_index.py"), *(extra or [])],
        capture_output=True, text=True, env=env,
    )


def _seed_review(root: Path, feedback_id: str, filename: str) -> Path:
    out = root / "ops" / "feedback" / "2026-05-22"
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    write(path, {
        "feedback_id": feedback_id,
        "agent": "atlas",
        "agent_type": "executor",
        "session_ref": "s-1",
        "created": "2026-05-22T10:00:00Z",
        "updated_at": "2026-05-22T10:00:00Z",
        "skill_version": "sha256:0123456789ab",
        "summary": "one line",
        "_draft": False,
        "below_threshold_count": 0,
        "items": [{
            "id": "it-1",
            "category": "script-defect",
            "layer": "skill",
            "location": {"file": "a.sh", "line": 4},
            "observation": "exits 1 unexpectedly",
            "suggested_fix": "add null guard",
            "severity": "medium",
            "frequency": "first-time",
            "evidence": "tool_call:abc123",
            "status": "open",
        }],
    }, "")
    return path


def _index_path(root: Path) -> Path:
    return root / "ops" / "feedback" / "_index" / "index.jsonl"


# ---------------------------------------------------------------------------
# 1. The index has a lock, and it is the index's own
# ---------------------------------------------------------------------------

def test_index_write_refuses_while_the_index_lock_is_held(tmp_path, monkeypatch):
    """A held index lock must stop the write, not let it race.

    Before C1.1 this test could not be written: there was no lock to hold.
    """
    root = tmp_path / "data"
    lock_dir = tmp_path / "locks"
    _seed_review(root, "fb-111111-aaaaaa", "atlas-one.md")
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    monkeypatch.setenv("LOCK_DIR", str(lock_dir))

    idx = _index_path(root)
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text("", encoding="utf-8")

    held = threading.Event()
    release = threading.Event()

    def holder():
        with with_lock(lock_path_for(index_lock_target()), timeout=5):
            held.set()
            release.wait(timeout=10)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert held.wait(timeout=5), "holder never took the index lock"
    try:
        result = _run_index(root, lock_dir,
                            env_extra={"CONCLAVE_INDEX_LOCK_TIMEOUT": "0"})
    finally:
        release.set()
        t.join(timeout=10)

    # Assert the refusal we mean, not merely the substring "lock": an argparse
    # "unrecognized arguments: --index-lock-timeout" ALSO contains it, and this test
    # passed on exactly that before the flag became an env knob.
    stderr = result.stderr or ""
    assert "unrecognized arguments" not in stderr, stderr
    assert result.returncode != 0, "a contended index write reported success"
    assert "could not acquire" in stderr.lower(), stderr
    assert idx.read_text(encoding="utf-8") == "", "index written while the lock was held"


def test_index_write_succeeds_once_the_lock_is_free(tmp_path):
    """The refusal above is contention, not a permanently wedged write path."""
    root = tmp_path / "data"
    lock_dir = tmp_path / "locks"
    _seed_review(root, "fb-222222-bbbbbb", "atlas-two.md")

    result = _run_index(root, lock_dir)

    assert result.returncode == 0, result.stderr
    rows = [json.loads(ln) for ln in _index_path(root).read_text().splitlines() if ln.strip()]
    assert any(r["feedback_id"] == "fb-222222-bbbbbb" for r in rows)


# ---------------------------------------------------------------------------
# 2. The named race: concurrent rebuilds never publish a torn file
# ---------------------------------------------------------------------------

def test_concurrent_rebuilds_leave_a_parseable_index(tmp_path):
    """Four concurrent rebuilds publish an index every line of which parses.

    Honest about its own strength: this is a SMOKE test, and it is not what pins the
    fix. Measured 2026-09-14 — with the index lock mutated out, it still passed; only
    `test_index_write_refuses_while_the_index_lock_is_held` (serialization) and
    `test_a_staged_tmp_never_collides_with_another_writers` (staging) reddened.
    Interleaving is not reproducible on demand, so it is evidence, never the guarantee.
    """
    root = tmp_path / "data"
    lock_dir = tmp_path / "locks"
    for n in range(12):
        _seed_review(root, f"fb-{n:06d}-cccccc", f"atlas-{n}.md")

    procs = [
        subprocess.Popen(
            [sys.executable, str(FEEDBACK_PKG / "feedback_index.py"), "--rebuild"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=_env(root, lock_dir),
        )
        for _ in range(4)
    ]
    for p in procs:
        p.wait(timeout=60)

    text = _index_path(root).read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            pytest.fail(f"torn index line {lineno}: {exc}: {line[:120]!r}")

    leftovers = list(_index_path(root).parent.glob("index.tmp*"))
    assert not leftovers, f"temporary files survived: {leftovers}"


# ---------------------------------------------------------------------------
# 3. Corruption is counted, not swallowed
# ---------------------------------------------------------------------------

def test_malformed_index_line_is_recorded_not_silently_dropped(tmp_path):
    """The instrumentation C1.0's window needs already had its detector: the
    incremental read hit `json.JSONDecodeError` and executed `pass`."""
    root = tmp_path / "data"
    lock_dir = tmp_path / "locks"
    _seed_review(root, "fb-333333-dddddd", "atlas-three.md")
    idx = _index_path(root)
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text('{"feedback_id": "fb-old-000000", "item_id": "it-1"}\n{"torn": \n',
                   encoding="utf-8")

    result = _run_index(root, lock_dir)
    assert result.returncode == 0, result.stderr

    log = idx.parent / "integrity.jsonl"
    assert log.is_file(), "no integrity log written for a malformed index line"
    events = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    malformed = [e for e in events if e.get("event") == "index.malformed_line"]
    assert malformed, f"malformed line not recorded; events={events}"
    assert malformed[0]["count"] == 1


def test_a_staged_tmp_never_collides_with_another_writers(tmp_path):
    """The fixed `index.tmp` is gone — deterministically, not probabilistically.

    The old write staged at `idx_path.with_suffix(".tmp")`, one name shared by every
    concurrent writer, and `os.replace` then published whichever half-written copy
    won. Occupying that exact path is what makes the difference observable without
    racing anything: the old code writes into it, `snapshot_write` stages at
    `.tmp.<pid>` and never looks.
    """
    root = tmp_path / "data"
    lock_dir = tmp_path / "locks"
    _seed_review(root, "fb-444444-eeeeee", "atlas-four.md")
    idx = _index_path(root)
    idx.parent.mkdir(parents=True, exist_ok=True)
    (idx.parent / "index.tmp").mkdir()  # the shared staging path, occupied

    result = _run_index(root, lock_dir)

    assert result.returncode == 0, result.stderr
    rows = [json.loads(ln) for ln in idx.read_text().splitlines() if ln.strip()]
    assert any(r["feedback_id"] == "fb-444444-eeeeee" for r in rows), rows
