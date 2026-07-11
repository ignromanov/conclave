"""snapshot.py — atomic write, TTL staleness, mkdir-lock, schema validation.
Port of lib/snapshot.sh. I/O-free core: no stdout, no CLI parsing, no process exit — pure file I/O.
"""
import os
import time
from pathlib import Path


def snapshot_write(path: Path, body: str) -> None:
    """Atomically write body to path via tmp sibling + os.replace.

    Creates parent dirs as needed. Leaves no *.tmp.* file on success or error.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(f"{path}.tmp.{os.getpid()}")
    try:
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        # os.replace already moved tmp → path; this is a no-op on success.
        # On error it cleans up the partially-written tmp file.
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def snapshot_is_stale(path: Path, ttl: int) -> bool:
    """Return True (stale) when: missing, size<100, age>=ttl, or mtime in future."""
    path = Path(path)
    if not path.exists():
        return True
    st = path.stat()
    if st.st_size < 100:
        return True
    now = time.time()
    mtime = st.st_mtime
    if mtime > now:  # clock skew — treat as stale
        return True
    if (now - mtime) >= ttl:
        return True
    return False


def acquire_lock(lock_dir: Path, timeout: int = 5) -> bool:
    """mkdir-based poll lock. Returns True on acquisition, False on timeout.

    Polls every 0.1s up to timeout*10 iterations (mirrors bash snapshot_acquire_lock).
    """
    lock_dir = Path(lock_dir)
    max_iters = timeout * 10
    for _ in range(max_iters):
        try:
            os.mkdir(lock_dir)
            return True
        except FileExistsError:
            time.sleep(0.1)
    return False


def release_lock(lock_dir: Path) -> None:
    """Best-effort rmdir; swallows all errors (mirrors bash snapshot_release_lock)."""
    try:
        os.rmdir(Path(lock_dir))
    except OSError:
        pass


def validate_schema(path: Path, expected_version) -> bool:
    """Return True iff file exists and contains a line 'schema_version: <expected_version>'.

    Mirrors bash: grep -qE "^schema_version: ${expected}$" "$path"
    Coerces expected_version to str for comparison.
    """
    path = Path(path)
    if not path.exists():
        return False
    needle = f"schema_version: {expected_version}"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == needle:
            return True
    return False
