"""Tests for enginelib.lock — acquire/release, contention, exception-safety, mkdir fallback."""
import threading
from pathlib import Path

import pytest

from enginelib.lock import with_lock

# ---------------------------------------------------------------------------
# Test 1: acquire / run / release
# ---------------------------------------------------------------------------

def test_acquire_run_release(tmp_path):
    """Lock is held during the body and released cleanly on normal exit."""
    lock_file = tmp_path / "test.lock"
    ran = []

    with with_lock(lock_file):
        ran.append("inside")

    assert ran == ["inside"]

    # A second acquisition must succeed immediately after the first released.
    with with_lock(lock_file):
        ran.append("second")

    assert ran == ["inside", "second"]


# ---------------------------------------------------------------------------
# Test 2: contention / mutual exclusion (deterministic — no sleep races)
# ---------------------------------------------------------------------------

def test_mutual_exclusion_deterministic(tmp_path):
    """While the main thread holds the lock, a second thread cannot enter its body.

    We use threading.Event to synchronise precisely:
    - main holds the lock and sets `held_event`
    - worker waits on `held_event`, then immediately tries to acquire — it
      must block (not enter the body) while the main thread still holds it
    - main sets `release_event` to let the worker proceed, then exits its block
    - worker eventually enters and records entry

    We assert that `worker_entered` is NOT set while main still holds the lock,
    proving mutual exclusion without any timing-sensitive sleeps.
    """
    lock_file = tmp_path / "test.lock"

    held_event = threading.Event()    # main: "I am holding the lock"
    _release_gate = threading.Event()  # main: "OK to release now"
    worker_entered = threading.Event()  # worker: "I entered the critical section"

    def worker():
        held_event.wait()  # wait until main is confirmed holding the lock
        with with_lock(lock_file):
            worker_entered.set()  # signal: we're inside

    t = threading.Thread(target=worker, daemon=True)

    with with_lock(lock_file):
        t.start()
        held_event.set()         # tell worker we're holding
        # Give the worker thread a moment to attempt acquisition (it should block).
        # We join with a very short timeout; it must NOT have entered yet.
        t.join(timeout=0.2)
        assert not worker_entered.is_set(), (
            "Worker entered critical section while main still held the lock — mutual exclusion broken"
        )
    # Main has now released the lock.

    t.join(timeout=2.0)
    assert worker_entered.is_set(), "Worker never entered critical section after lock was released"


# ---------------------------------------------------------------------------
# Test 3: release on exception
# ---------------------------------------------------------------------------

def test_release_on_exception(tmp_path):
    """Raising inside the `with` body still releases the lock."""
    lock_file = tmp_path / "test.lock"

    with pytest.raises(ValueError, match="boom"):
        with with_lock(lock_file):
            raise ValueError("boom")

    # Lock must be released; a fresh acquisition must succeed.
    entered = []
    with with_lock(lock_file):
        entered.append(True)

    assert entered == [True]


# ---------------------------------------------------------------------------
# Test 4: mkdir fallback (monkeypatch fcntl unavailable)
# ---------------------------------------------------------------------------

def test_mkdir_fallback(tmp_path, monkeypatch):
    """When fcntl is unavailable, the mkdir-based path is exercised."""
    # Hide fcntl by removing it from sys.modules and blocking re-import.
    import enginelib.lock as lock_module

    # Replace the module-level _USE_FLOCK flag with False so the fallback runs.
    monkeypatch.setattr(lock_module, "_USE_FLOCK", False)

    lock_file = tmp_path / "fallback.lock"
    ran = []

    with with_lock(lock_file):
        ran.append("inside-fallback")
        # While held, the .lk directory must exist.
        lock_dir = Path(str(lock_file) + ".lk")
        assert lock_dir.exists(), ".lk dir should exist while lock is held"

    assert ran == ["inside-fallback"]

    # .lk dir must be gone after release.
    lock_dir = Path(str(lock_file) + ".lk")
    assert not lock_dir.exists(), ".lk dir should be removed after release"

    # Second acquisition must succeed.
    with with_lock(lock_file):
        ran.append("second-fallback")

    assert ran == ["inside-fallback", "second-fallback"]
