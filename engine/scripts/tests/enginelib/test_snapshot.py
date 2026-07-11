"""Tests for enginelib.snapshot — port of tests/lib/snapshot.bats (10 cases + clock-skew).

Bats → Python mapping:
  bash return 0 (stale / acquired / match)  → Python True
  bash return 1 (fresh / timeout / mismatch) → Python False

Age is simulated deterministically via os.utime; no sleeps for timing.
"""
import os
import threading
import time

from enginelib.snapshot import (
    acquire_lock,
    release_lock,
    snapshot_is_stale,
    snapshot_write,
    validate_schema,
)

# ---------------------------------------------------------------------------
# 1. Atomic write
# ---------------------------------------------------------------------------

def test_snapshot_write_content_no_tmp_leftover(tmp_path):
    """Bats case 1: produces file with expected content, no .tmp.* leftover."""
    target = tmp_path / "sx.txt"

    snapshot_write(target, "hello")

    assert target.is_file()
    assert target.read_text() == "hello"

    leftovers = list(tmp_path.glob("*.tmp.*"))
    assert leftovers == [], f"tmp files left behind: {leftovers}"


def test_snapshot_write_creates_parent_dir(tmp_path):
    """Bats case 2: creates parent directory if missing."""
    target = tmp_path / "nested" / "dir" / "file.md"

    snapshot_write(target, "body")

    assert target.is_file()


# ---------------------------------------------------------------------------
# 2. TTL stale detection
# ---------------------------------------------------------------------------

def test_snapshot_is_stale_fresh_file(tmp_path):
    """Bats case 3: fresh file (mtime=now, size>=100) returns False (fresh).
    Bash: snapshot_is_stale returns 1 (fresh) → Python False."""
    f = tmp_path / "fresh.md"
    f.write_text("." * 110)  # 110 bytes, mtime=now

    assert snapshot_is_stale(f, 60) is False


def test_snapshot_is_stale_missing_file(tmp_path):
    """Bats case 4: missing file returns True (stale).
    Bash: returns 0 (stale) → Python True."""
    assert snapshot_is_stale(tmp_path / "nonexistent.md", 60) is True


def test_snapshot_is_stale_aged_file(tmp_path):
    """Bats case 5: aged file (mtime 120s ago, ttl=60) returns True (stale).
    Bash: returns 0 (stale) → Python True. Age simulated via os.utime."""
    f = tmp_path / "old.md"
    f.write_text("." * 110)
    past = time.time() - 120
    os.utime(f, (past, past))

    assert snapshot_is_stale(f, 60) is True


# ---------------------------------------------------------------------------
# 3. Byte-size threshold
# ---------------------------------------------------------------------------

def test_snapshot_is_stale_small_file(tmp_path):
    """Bats case 6: fresh mtime but size < 100 bytes returns True (stale).
    Bash: returns 0 (stale) → Python True."""
    f = tmp_path / "small.md"
    f.write_text("." * 50)  # 50 bytes < 100 threshold

    assert snapshot_is_stale(f, 9999) is True


# ---------------------------------------------------------------------------
# 4. Clock-skew (behavior from lib/snapshot.sh §clock-skew, no bats case)
# ---------------------------------------------------------------------------

def test_snapshot_is_stale_clock_skew(tmp_path):
    """Extra: mtime in the future (clock skew) returns True (stale)."""
    f = tmp_path / "future.md"
    f.write_text("." * 110)
    future = time.time() + 3600  # 1 hour ahead
    os.utime(f, (future, future))

    assert snapshot_is_stale(f, 9999) is True


# ---------------------------------------------------------------------------
# 5. mkdir-lock concurrency
# ---------------------------------------------------------------------------

def test_acquire_lock_race(tmp_path):
    """Bats case 7: exactly one of two racing acquirers wins (the other times out).
    Uses threading to mirror the two background subshells in the bats test."""
    lock_dir = tmp_path / "race.lock.d"
    results: list[bool | None] = [None, None]

    def try_acquire(idx: int) -> None:
        results[idx] = acquire_lock(lock_dir, timeout=1)

    t1 = threading.Thread(target=try_acquire, args=(0,))
    t2 = threading.Thread(target=try_acquire, args=(1,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one winner (True), one loser (False).
    assert (results[0] is True and results[1] is False) or (
        results[0] is False and results[1] is True
    ), f"Expected one True and one False, got {results}"

    # Release whichever lock was held.
    release_lock(lock_dir)


# ---------------------------------------------------------------------------
# 6. schema_version validation
# ---------------------------------------------------------------------------

def test_validate_schema_matching_version(tmp_path):
    """Bats case 8: matching version returns True.
    Bash: returns 0 (match) → Python True."""
    f = tmp_path / "schema_ok.md"
    f.write_text("---\nschema_version: 1\ntitle: test\n---\nbody\n")

    assert validate_schema(f, 1) is True


def test_validate_schema_mismatched_version(tmp_path):
    """Bats case 9: mismatched version returns False.
    Bash: returns 1 (mismatch) → Python False."""
    f = tmp_path / "schema_bad.md"
    f.write_text("---\nschema_version: 2\ntitle: test\n---\nbody\n")

    assert validate_schema(f, 1) is False


def test_validate_schema_missing_key(tmp_path):
    """Bats case 10: missing schema_version returns False.
    Bash: returns 1 (mismatch) → Python False."""
    f = tmp_path / "no_schema.md"
    f.write_text("---\ntitle: test\n---\nbody\n")

    assert validate_schema(f, 1) is False
