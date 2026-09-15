"""enginelib.integrity — a log of corruption and contention events, only ever added to.

Opens the 30-day window spec 118's C1.0 needs. Deliberately not a metrics system:
one JSON object per line, appended with O_APPEND so concurrent writers interleave
whole lines rather than fragments, and never raising — an instrument that can sink
the operation it measures is worse than no instrument.

The caller supplies the log path. This module resolves no roots: the tree already
has seven root resolvers that have measurably drifted (GH#107), and an eighth hidden
inside an instrument is the last place anyone would look for it.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def record(log_path: Path | str, event: str, **fields) -> None:
    """Append one event to *log_path*. Never raises."""
    try:
        payload = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": event,
            "pid": os.getpid(),
            **fields,
        }
        line = json.dumps(payload, sort_keys=True, default=str) + "\n"
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # O_APPEND: the kernel places each write at the current end of file, so two
        # writers cannot overwrite one another's line. One write() per event keeps
        # the line whole; no lock is taken, because a lock around the instrument
        # would serialize the very contention it exists to observe.
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001 — an instrument may never sink its subject
        pass


def log_path_beside(target: Path | str) -> Path:
    """The integrity log for *target*: `integrity.jsonl` in the same directory."""
    return Path(target).parent / "integrity.jsonl"
