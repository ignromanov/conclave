"""walk.py — one tree walk for the eval apparatus, pruned rather than filtered.

`Path.rglob` cannot prune: it descends into a directory and only then are its paths
discarded by the caller's filter. Two costs follow, and the second is the one that bit.

1. Wasted traversal. A fixture root carries a real `.git` (`fixture.py` runs `git init`
   on it so `git status` works inside, which is an artificiality cue no transcript
   classifier catches), and every scan walked all of it to throw all of it away.

2. A race. While git packs objects, `.git/objects/<xx>` can vanish mid-scan, and it is
   the WALK ITSELF that raises `FileNotFoundError` — a per-file `except OSError` inside
   the loop body never gets the chance to run. Python 3.13 rewrote pathlib globbing onto
   `os.scandir` with the error suppressed, so the same tree raises on 3.11 and is silently
   walked short on 3.13. Measured 2026-09-15, five trials each: 3.11.14 raised 5/5;
   3.13.7 and 3.14.5 suppressed 3/3. That is the worse half — a leak check that cannot
   finish its walk still reports "no leaks".

`snapshot.py` already diagnosed this and fixed it for itself; `fixture.py` and `traps.py`
kept the unpruned walk. This module is that fix with one owner instead of one copy.

Pruning `.git` loses no coverage here. The scans want text files that restate the charter
or name a real path, and a git object is neither: it has no suffix the scans accept and it
is zlib-compressed. Nor can `.git` hide the charter itself — `fixture.py` runs `git init`
AFTER the strip, so the objects hold only already-stripped content.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

# Directories that are machinery, never subject matter. `.git` is the one that races; the
# caches are here because walking them is pure cost and a stale `.pyc` is not a leak.
SKIP_DIRS = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv",
})


def walk_files(root: Path) -> Iterator[Path]:
    """Every file under `root`, pruning `SKIP_DIRS` during the walk.

    `os.walk` defaults to `onerror=None`, which swallows a scandir failure: a directory
    that disappears in a tree we DO care about drops out of the walk instead of aborting
    the caller. That is the same trade `snapshot.py` made — a scan that returns what it
    could reach beats one that raises — and it is only tolerable because the directory
    that actually vanishes, `.git/objects/<xx>`, is pruned above and never reached.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name
