"""Tests for enginelib.lock — acquire/release, contention, exception-safety, mkdir fallback."""
import threading
from pathlib import Path

import pytest

from enginelib.lock import LockTimeout, lock_path_for, with_lock

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


# ---------------------------------------------------------------------------
# Test 6 (118 C1.1): bounded acquisition — the semantics snapshot.acquire_lock had
# ---------------------------------------------------------------------------

def test_timeout_zero_acquires_a_free_lock(tmp_path):
    """timeout=0 is 'try once', not 'never try'. A free lock is taken immediately.

    snapshot.acquire_lock(dir, 0) made ZERO attempts and always reported failure,
    which is why the triage test had to pre-create the lock dir to see a refusal.
    """
    ran = []
    with with_lock(tmp_path / "free.lock", timeout=0):
        ran.append("inside")
    assert ran == ["inside"]


def test_timeout_raises_lock_timeout_when_held(tmp_path):
    """A held lock makes a bounded acquisition raise instead of blocking forever.

    This is the migration's whole risk: the five sites moving off acquire_lock all
    degrade gracefully on contention, and with_lock's default LOCK_EX would have
    turned 'give up after 5s' into 'hang at every session start'.
    """
    lock_file = tmp_path / "held.lock"
    held = threading.Event()
    release = threading.Event()

    def holder():
        with with_lock(lock_file):
            held.set()
            release.wait(timeout=5)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert held.wait(timeout=5), "holder never acquired the lock"

    try:
        with pytest.raises(LockTimeout):
            with with_lock(lock_file, timeout=0):
                pytest.fail("acquired a lock another thread holds")
    finally:
        release.set()
        t.join(timeout=5)

    # The holder released: the same bounded call now succeeds.
    with with_lock(lock_file, timeout=0):
        pass


def test_lock_timeout_is_a_timeout_error(tmp_path):
    """LockTimeout stays catchable as TimeoutError — the mkdir fallback already
    raised TimeoutError, and callers written against it must not break."""
    assert issubclass(LockTimeout, TimeoutError)


# ---------------------------------------------------------------------------
# Test 7 (118 C1.1): lock_path_for — the LOCK_DIR convention, promoted
# ---------------------------------------------------------------------------

def test_lock_path_for_keeps_the_lock_out_of_the_target_tree(tmp_path, monkeypatch):
    """A lock beside its target lands in the tracked DATA tree: .triage-lock is not
    gitignored, so a crashed holder leaves both a wedge and a commit candidate."""
    monkeypatch.setenv("LOCK_DIR", str(tmp_path / "locks"))
    target = tmp_path / "data" / "ops" / "feedback" / "_index" / "index.jsonl"
    target.parent.mkdir(parents=True)

    lock = lock_path_for(target)

    assert (tmp_path / "locks") in lock.parents
    assert target.parent not in lock.parents


def test_lock_path_for_distinguishes_targets(tmp_path, monkeypatch):
    """Two instances on one machine must not share a lock — the key is the target's
    resolved path, not a fixed basename."""
    monkeypatch.setenv("LOCK_DIR", str(tmp_path / "locks"))
    a = tmp_path / "instance-a" / "index.jsonl"
    b = tmp_path / "instance-b" / "index.jsonl"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)

    assert lock_path_for(a) != lock_path_for(b)
    assert lock_path_for(a) == lock_path_for(a)


def test_lock_path_for_actually_excludes(tmp_path, monkeypatch):
    """The path is not decoration: two holders of the same derived path exclude."""
    monkeypatch.setenv("LOCK_DIR", str(tmp_path / "locks"))
    target = tmp_path / "index.jsonl"
    target.write_text("", encoding="utf-8")

    with with_lock(lock_path_for(target), timeout=0):
        with pytest.raises(LockTimeout):
            _second_holder_must_fail(lock_path_for(target))


def _second_holder_must_fail(path: Path) -> None:
    """flock fds are independent even inside one process, so this really contends."""
    result: list[BaseException | None] = [None]

    def attempt() -> None:
        try:
            with with_lock(path, timeout=0):
                pass
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller's thread
            result[0] = exc

    t = threading.Thread(target=attempt)
    t.start()
    t.join(timeout=5)
    if result[0] is not None:
        raise result[0]
