"""scans/ — one module per briefing section.

Each module exposes a single ``build(ctx) -> str`` function.
``ctx`` is a :class:`ScanCtx` dataclass carrying all resolved paths
needed by every scan.  It is constructed once in the caller (render.py
or the CLI) and threaded through all build() calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScanCtx:
    """Resolved runtime context for a single advisor briefing build.

    All Path fields are absolute and already resolved at construction time.

    Attributes:
        advisor:           Canonical advisor name (e.g. "kai-cto").
        short_name:        First segment before "-" (e.g. "kai").
        repo_root:         Absolute path to the .ai/ repo root.
        decisions_dir:     agent-memory/advisors/decisions/
        sessions_dir:      agent-memory/advisors/sessions/
        mentions_dir:      agent-memory/advisors/mentions/
        gh_cache_dir:      agent-memory/gh-cache/
        personality_path:  .claude/skills/team.<advisor>/memory/personality.md
        progress_path:     <repo_root>/progress-summary.md
    """

    advisor: str
    short_name: str
    repo_root: Path
    decisions_dir: Path
    sessions_dir: Path
    mentions_dir: Path
    gh_cache_dir: Path
    personality_path: Path
    progress_path: Path
