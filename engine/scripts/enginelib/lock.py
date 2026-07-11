"""enginelib.lock — advisory exclusive lock as a context manager.

Primary path:  fcntl.flock  (POSIX, including macOS)
Fallback path: mkdir-based lock (for platforms without fcntl, e.g. Windows)

Usage:
    from enginelib.lock import with_lock

    with with_lock("/tmp/my.lock"):
        ...  # exclusive critical section; released on exit, even on exception

Environment knobs (mirrored from lib/lock.sh):
    LOCK_TRIES   retries for the mkdir fallback (default: 20)
    LOCK_SLEEP   seconds between retries (default: 0.1)
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


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@contextlib.contextmanager
def _flock_lock(lock_file: Path):
    fd = open(lock_file, "w", encoding="utf-8")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


@contextlib.contextmanager
def _mkdir_lock(lock_file: Path):
    """mkdir-based fallback: atomic os.mkdir for the lock, os.rmdir to release."""
    lock_dir = Path(str(lock_file) + ".lk")
    tries = int(os.environ.get("LOCK_TRIES", 20))
    sleep = float(os.environ.get("LOCK_SLEEP", 0.1))

    acquired = False
    for _ in range(tries):
        try:
            os.mkdir(lock_dir)
            acquired = True
            break
        except FileExistsError:
            time.sleep(sleep)

    if not acquired:
        raise TimeoutError(
            f"with_lock: could not acquire lock after {tries} tries: {lock_file}"
        )

    try:
        yield
    finally:
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass


@contextlib.contextmanager
def with_lock(lock_path: "Path | str"):
    """Acquire an exclusive advisory lock on *lock_path*, yield, then release.

    Uses fcntl.flock when available (Linux/macOS); falls back to mkdir-based
    locking on platforms where fcntl is absent (e.g. Windows).

    Raises TimeoutError if the mkdir fallback exhausts its retries.
    Never prints; errors are raised as exceptions.
    """
    p = Path(lock_path)
    _ensure_parent(p)

    if _USE_FLOCK:
        with _flock_lock(p):
            yield
    else:
        with _mkdir_lock(p):
            yield
