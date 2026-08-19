"""paths.py — re-export of the single DATA/CODE root resolver in `enginelib.paths`.

This module used to carry its own port of the same bash function. The two ports then
drifted on five axes: which env names counted, whether the answer was `.resolve()`d,
what the filesystem walk started from, whether a symlinked `.claude` was accepted, and
a module-level cache only this one had. Its public surface was a strict subset of
`enginelib.paths` and every shared helper built the same tree, so the drift produced
two spellings of one directory rather than two directories — which is worse, because
`==` between them was false while both were "right".

`briefing/` and `feedback/` import from here; `engine/cmd/` and `lifecycle/` import
from `enginelib.paths`. `feedback_verify.py` imports from both in one function. The
names stay so those twelve call sites keep working; the answers now come from one
place. See `tests/test_root_resolver_agreement.py`, which fails if they ever part again.

The module-level `_REPO_ROOT_CACHE` is gone with the walk it memoised. `repo_root()`
is a couple of `os.environ` reads plus, at most, one walk up the cwd — never worth a
cache that has to be cleared in five test files to keep it honest.
"""
from __future__ import annotations

from enginelib.paths import (
    advisors_memory_dir,
    agent_memory_dir,
    briefings_dir,
    decisions_dir,
    engine_root,
    executors_memory_dir,
    gh_cache_dir,
    git_cache_dir,
    handoffs_dir,
    hot_md_path,
    mentions_dir,
    repo_root,
    run_log_dir,
    sessions_dir,
    templates_dir,
)

__all__ = [
    "advisors_memory_dir",
    "agent_memory_dir",
    "briefings_dir",
    "decisions_dir",
    "engine_root",
    "executors_memory_dir",
    "gh_cache_dir",
    "git_cache_dir",
    "handoffs_dir",
    "hot_md_path",
    "mentions_dir",
    "repo_root",
    "run_log_dir",
    "sessions_dir",
    "templates_dir",
]
