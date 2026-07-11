"""paths.py — repo-root + canonical directory resolution.

Port of lib/paths.sh. All functions return pathlib.Path objects.
Respects the CONCLAVE_AI_ROOT environment variable (VOIDPAY_AI_ROOT back-compat
alias) for test overrides.
"""
from __future__ import annotations

import os
from pathlib import Path

# Module-level mutable cache; cleared in tests via:
#   monkeypatch.setattr("briefing.paths._REPO_ROOT_CACHE", None)
_REPO_ROOT_CACHE: Path | None = None


def repo_root() -> Path:
    """Return the .ai/ repo root as an absolute Path.

    Resolution order:
    1. CONCLAVE_AI_ROOT env variable (VOIDPAY_AI_ROOT back-compat alias) — test override.
    2. Walk up from this file's location until ops/ + .claude/ are both present
       as non-symlink directories (mirrors the bash logic in lib/paths.sh).

    Result is module-cached after the first successful call.
    """
    global _REPO_ROOT_CACHE

    env_override = os.environ.get("CONCLAVE_AI_ROOT") or os.environ.get("VOIDPAY_AI_ROOT")
    if env_override:
        return Path(env_override).resolve()

    # Plugin mode (098 D-5): under Claude Code DATA defaults to the consumer's
    # .conclave/. Guarded on CLAUDE_PROJECT_DIR so in-repo runs (var absent) fall
    # through to the filesystem walk below.
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return (Path(project_dir) / ".conclave").resolve()

    if _REPO_ROOT_CACHE is not None:
        return _REPO_ROOT_CACHE

    cur = Path(__file__).resolve().parent
    while cur != cur.parent:
        ops = cur / "ops"
        claude = cur / ".claude"
        # Real .ai/ has ops/ as a real dir; worktree roots have .claude/ as symlink.
        if ops.is_dir() and not ops.is_symlink() and claude.exists():
            _REPO_ROOT_CACHE = cur
            return cur
        cur = cur.parent

    raise RuntimeError(
        "repo_root: unable to locate .ai root "
        "(set CONCLAVE_AI_ROOT or run from inside an instance root)"
    )


def agent_memory_dir() -> Path:
    return repo_root() / "agent-memory"


def advisors_memory_dir() -> Path:
    return agent_memory_dir() / "advisors"


def executors_memory_dir() -> Path:
    return agent_memory_dir() / "executors"


def briefings_dir() -> Path:
    return advisors_memory_dir() / "briefings"


def sessions_dir() -> Path:
    return advisors_memory_dir() / "sessions"


def decisions_dir() -> Path:
    return advisors_memory_dir() / "decisions"


def mentions_dir() -> Path:
    return advisors_memory_dir() / "mentions"


def feedback_dir() -> Path:
    return advisors_memory_dir() / "feedback"


def feedback_archive_dir() -> Path:
    return advisors_memory_dir() / "feedback" / "archive"


def handoffs_dir() -> Path:
    return repo_root() / "ops" / "handoffs"


def gh_cache_dir() -> Path:
    return agent_memory_dir() / "gh-cache"


def git_cache_dir() -> Path:
    return agent_memory_dir() / "git-cache"


def run_log_dir() -> Path:
    return agent_memory_dir() / "run-log"


def engine_root() -> Path:
    """Return the engine/ CODE root as an absolute Path.

    Forge templates/protocols/references are CODE, not per-instance DATA — they
    live in the engine FLAT layout, never under a DATA-root `.claude/`. Derived
    from this file's location (engine/scripts/briefing/paths.py -> engine/),
    CWD-independent; CONCLAVE_ENGINE_ROOT overrides (mirrors lib/paths.sh).
    """
    env_override = os.environ.get("CONCLAVE_ENGINE_ROOT")
    if env_override:
        return Path(env_override).resolve()
    # Plugin mode (098 D-5): ENGINE is the engine subtree under the plugin install
    # dir. Guarded on CLAUDE_PLUGIN_ROOT so in-repo runs derive from file location.
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        return (Path(plugin_root) / "engine").resolve()
    return Path(__file__).resolve().parents[2]


def templates_dir() -> Path:
    return engine_root().parent / "skills" / "forge-operations" / "references" / "templates"


def hot_md_path() -> Path:
    return agent_memory_dir() / "hot.md"
