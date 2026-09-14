"""enginelib.lock — advisory exclusive lock as a context manager.

Primary path:  fcntl.flock  (POSIX, including macOS)
Fallback path: mkdir-based lock (for platforms without fcntl, e.g. Windows)

Usage:
    from enginelib.lock import lock_path_for, with_lock

    with with_lock("/tmp/my.lock"):
        ...  # exclusive critical section; released on exit, even on exception

    with with_lock(lock_path_for(index_path), timeout=5):
        ...  # bounded: raises LockTimeout instead of waiting forever

Environment knobs (mirrored from lib/lock.sh):
    LOCK_TRIES   retries for the mkdir fallback when no timeout is given (default: 20)
    LOCK_SLEEP   seconds between retries (default: 0.1)
    LOCK_DIR     where lock_path_for() puts locks (default: /tmp/conclave-locks)
"""

import contextlib
import os
import time
from pathlib import Path

try:
    import fcntl
    _USE_FLOCK = True
except ImportError:
    _USE_FLOCK = False

_POLL = 0.05


class LockTimeout(TimeoutError):
    """Raised when a bounded acquisition expires.

    Subclasses TimeoutError: the mkdir fallback already raised TimeoutError, so
    callers written against that keep working.
    """


def lock_path_for(target: "Path | str") -> Path:
    """Return the lock file guarding *target*, under LOCK_DIR and keyed by its path.

    A lock beside its target is a lock inside the tracked DATA tree — `.triage-lock`
    is not gitignored, so a crashed holder leaves both a wedge and a commit candidate.
    Keying by the resolved path (rather than a fixed basename) is what keeps two
    instances on one machine from sharing a lock.
    """
    key = str(Path(target).resolve()).replace(os.sep, "_").lstrip("_")
    return Path(os.environ.get("LOCK_DIR", "/tmp/conclave-locks")) / f"{key}.lock"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@contextlib.contextmanager
def _flock_lock(lock_file: Path, timeout: "float | None"):
    # "a+" rather than "w": truncating is pointless for a lock file and destructive
    # if a caller ever points this at something that is not one.
    fd = open(lock_file, "a+", encoding="utf-8")
    try:
        if timeout is None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise LockTimeout(
                            f"with_lock: lock held by another process after "
                            f"{timeout}s: {lock_file}"
                        ) from None
                    time.sleep(_POLL)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        fd.close()


@contextlib.contextmanager
def _mkdir_lock(lock_file: Path, timeout: "float | None"):
    """mkdir-based fallback: atomic os.mkdir for the lock, os.rmdir to release."""
    lock_dir = Path(str(lock_file) + ".lk")

    # One budget, expressed one way. The earlier shape carried a `tries` counter AND a
    # `deadline`, exactly one of them set — an invariant only the control flow knew,
    # which is why mypy read the decrement as `None - int` and was right to.
    if timeout is None:
        sleep = float(os.environ.get("LOCK_SLEEP", 0.1))
        deadline = time.monotonic() + int(os.environ.get("LOCK_TRIES", 20)) * sleep
    else:
        sleep = _POLL
        deadline = time.monotonic() + timeout

    acquired = False
    while True:
        try:
            os.mkdir(lock_dir)
            acquired = True
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                break
            time.sleep(sleep)

    if not acquired:
        raise LockTimeout(f"with_lock: could not acquire lock: {lock_file}")

    try:
        yield
    finally:
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass


@contextlib.contextmanager
def with_lock(lock_path: "Path | str", timeout: "float | None" = None):
    """Acquire an exclusive advisory lock on *lock_path*, yield, then release.

    Uses fcntl.flock when available (Linux/macOS); falls back to mkdir-based
    locking on platforms where fcntl is absent (e.g. Windows).

    *timeout* is the bounded-acquisition knob that `snapshot.acquire_lock` carried
    and plain LOCK_EX does not: None waits indefinitely (the original behaviour, and
    what hot.md and the duty ledger want); a number polls to a deadline and then
    raises LockTimeout, so a caller that degrades on contention still can. timeout=0
    means "try once", which on a free lock succeeds.

    Never prints; errors are raised as exceptions.
    """
    if timeout is not None and timeout < 0:
        raise ValueError(f"with_lock: timeout must be >= 0, got {timeout}")

    p = Path(lock_path)
    _ensure_parent(p)

    if _USE_FLOCK:
        with _flock_lock(p, timeout):
            yield
    else:
        with _mkdir_lock(p, timeout):
            yield
