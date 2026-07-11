"""enginelib/find.py — find_references: grep-equivalent over engine_root()/.claude + CLAUDE.md.

Port of engine/scripts/find-references.sh (22 lines).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_PRUNE = {".git", "archive", "node_modules"}


def find_references(pattern: str, engine_root: Path) -> list[str]:
    """Return list of 'path:lineno:line' matches for *pattern* (extended regex).

    Search order (faithful to the bash ROOTS array):
    1. engine_root/.claude  — recursive walk, pruning .git/archive/node_modules
    2. engine_root/CLAUDE.md — single file

    Missing roots are silently skipped (matches `[[ -e "$root" ]] || continue`).
    Exit-0-on-no-match is the caller's responsibility (this is I/O-free).
    """
    rx = re.compile(pattern)
    results: list[str] = []

    dot_claude = engine_root / ".claude"
    if dot_claude.is_dir():
        for dirpath, dirnames, filenames in os.walk(dot_claude):
            # Prune excluded dirs in-place so os.walk won't descend into them.
            dirnames[:] = sorted(d for d in dirnames if d not in _PRUNE)
            for name in sorted(filenames):
                path = Path(dirpath) / name
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for lineno, raw in enumerate(text.splitlines(), start=1):
                    if rx.search(raw):
                        results.append(f"{path}:{lineno}:{raw}")

    claude_md = engine_root / "CLAUDE.md"
    if claude_md.is_file():
        try:
            text = claude_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if rx.search(raw):
                results.append(f"{claude_md}:{lineno}:{raw}")

    return results
