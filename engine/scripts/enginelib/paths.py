"""paths.py — path constants & directory helpers. Port of lib/paths.sh.

Env convention (locked 1af117c): CONCLAVE_ENGINE_ROOT = the engine/ dir;
plugin skills live at engine_root().parent/skills. The ':+' guards from
lib/paths.sh:121-122 are mirrored: a CC var injects the default ONLY when set.
"""
import os
from collections.abc import Iterator
from pathlib import Path


def _plugin_data_default() -> str | None:
    base = os.environ.get("CLAUDE_PROJECT_DIR")
    return f"{base}/.conclave" if base else None


def _plugin_engine_default() -> str | None:
    base = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return f"{base}/engine" if base else None


def repo_root(start: Path | None = None) -> Path:
    """DATA root. Env override (CONCLAVE_AI_ROOT, then CLAUDE_PROJECT_DIR/.conclave),
    else walk up from `start` for a dir with non-symlink ops/ + .claude/ siblings."""
    env = os.environ.get("CONCLAVE_AI_ROOT") or _plugin_data_default()
    if env:
        return Path(env)
    cur = (start or Path.cwd()).resolve()
    for d in (cur, *cur.parents):
        ops, claude = d / "ops", d / ".claude"
        if ops.is_dir() and not ops.is_symlink() and claude.is_dir() and not claude.is_symlink():
            return d
    raise RuntimeError(
        "repo_root: unable to locate .ai root (set CONCLAVE_AI_ROOT or run from inside .ai/)")


def engine_root() -> Path:
    """CODE root = the engine/ dir. Env override, else derive from this file's
    location: __file__ = engine/scripts/enginelib/paths.py, so parents[2] == engine/
    (parents[0]=enginelib, parents[1]=scripts, parents[2]=engine)."""
    env = os.environ.get("CONCLAVE_ENGINE_ROOT") or _plugin_engine_default()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]   # enginelib/ -> scripts/ -> engine/


def plugin_agents_dir() -> Path:
    """Plugin-shipped agent-defs (canonical: forge; plus exec-*). Sibling of engine/."""
    return engine_root().parent / "agents"


def project_root() -> Path:
    """Project root (the dir that holds .claude/). CLAUDE_PROJECT_DIR if set; else the
    PARENT of a `.conclave` DATA root (repo_root()), since .claude/ is a sibling of the
    DATA root under the plugin; else repo_root() itself for in-repo / test layouts where
    the DATA root and project root coincide."""
    base = os.environ.get("CLAUDE_PROJECT_DIR")
    if base:
        return Path(base)
    root = repo_root()
    return root.parent if root.name == ".conclave" else root


def consumer_git_cwd() -> str | None:
    """Working directory for `git` subprocesses that must read the CONSUMER's repository.

    `CONCLAVE_GIT_REMOTE_CWD` (the existing test/ops seam), else `CLAUDE_PROJECT_DIR`, else
    None — letting git use the process cwd, which is the right answer only when neither is
    set (a dev/dogfood run standing in the project).

    Both reads treat an EMPTY value as unset. `export CONCLAVE_GIT_REMOTE_CWD=` must not
    silently restore the process cwd, which is the leak this exists to close.

    Defaulting HERE rather than at call sites covers every caller by construction: the
    lifecycle verbs are invoked straight from advisor command prose and pin nothing
    themselves. One resolver for both git-reading verbs, so `gh-fetch`'s repo-scope
    fallback and `git-fetch`'s session snapshot cannot drift onto different rules — they
    did, and `git-fetch` wrote the engine's branch and the maintainer's worktree paths into
    every consumer's DATA tree for as long as they were separate.
    """
    return (
        os.environ.get("CONCLAVE_GIT_REMOTE_CWD")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or None
    )


def project_claude_dir() -> Path:
    """Project-side .claude/ dir (agents, skills, settings, CLAUDE.md). Sibling of the
    .conclave DATA root under the plugin; <root>/.claude for in-repo / test layouts."""
    return project_root() / ".claude"


def project_agents_dir() -> Path:
    """Project hired agent-defs (.claude/agents/)."""
    return project_claude_dir() / "agents"


def project_skills_dir() -> Path:
    """Project-side skills dir (.claude/skills/, live-reloaded router homes)."""
    return project_claude_dir() / "skills"


# Advisor SKILL-dir naming: current mint is `conclave-<id>` (router.py); legacy
# hires used `team.<id>`. During the #48 migration readers must tolerate both.
_ADVISOR_SKILL_PREFIXES = ("conclave-", "team.")


def advisor_skill_dir(advisor_id: str, skills_base: Path | None = None) -> Path:
    """Resolve an advisor's SKILL directory, tolerating both the current
    `conclave-<id>` and legacy `team.<id>` layouts (#48).

    Returns the first existing dir, preferring the canonical `conclave-` prefix;
    when neither exists, returns the canonical `conclave-<id>` path so fresh
    provisioning always lands on the current layout. `skills_base` defaults to
    the project `.claude/skills/` where `advisor create` mints routers.
    """
    base = skills_base if skills_base is not None else project_skills_dir()
    for prefix in _ADVISOR_SKILL_PREFIXES:
        candidate = base / f"{prefix}{advisor_id}"
        if candidate.is_dir():
            return candidate
    return base / f"conclave-{advisor_id}"


def iter_advisor_skills(skills_base: Path | None = None) -> Iterator[tuple[str, Path]]:
    """Discover advisor SKILL dirs across both the canonical `conclave-<id>` and
    legacy `team.<id>` layouts (#54 — the read-side twin of `advisor_skill_dir`).

    Yields `(bare_id, skill_md_path)` per advisor, deduped by bare id (canonical
    `conclave-` wins when both layouts exist), globally sorted by bare id for
    deterministic output. Lifecycle skills are NOT filtered — callers apply their
    own bare-id exclusion sets, whose semantics differ (bloat exempts quorum;
    phantom/versions only skip lifecycle). `skills_base` defaults to the project
    `.claude/skills/` where `advisor create` mints routers.
    """
    base = skills_base if skills_base is not None else project_skills_dir()
    found: dict[str, Path] = {}
    for prefix in _ADVISOR_SKILL_PREFIXES:  # conclave- first → wins on collision
        for skill_md in base.glob(f"{prefix}*/SKILL.md"):
            if skill_md.is_file():
                found.setdefault(skill_md.parent.name[len(prefix):], skill_md)
    for bare in sorted(found):
        yield bare, found[bare]


def iter_advisor_authored_files(skills_base: Path | None = None) -> Iterator[tuple[str, Path]]:
    """Yield `(bare_id, md_path)` for every advisor-*authored* markdown file — the
    SKILL.md router PLUS `memory/*.md` and `references/**/*.md` — across both layout
    prefixes (the write-side twin scope of `iter_advisor_skills`, #3).

    Unlike `iter_advisor_skills` (one deduped SKILL.md per advisor), this UNIONS files
    from both `conclave-<id>` and `team.<id>` dirs under the same bare id: during the
    #48 migration an advisor's router can live under `conclave-` while its rich content
    (personality.md, references) still sits under `team.-`. Ordered by (prefix, dir,
    file) for deterministic output. Callers apply their own lifecycle exclusion.
    """
    base = skills_base if skills_base is not None else project_skills_dir()
    for prefix in _ADVISOR_SKILL_PREFIXES:
        for adv_dir in sorted(base.glob(f"{prefix}*")):
            if not adv_dir.is_dir():
                continue
            bare = adv_dir.name[len(prefix):]
            skill_md = adv_dir / "SKILL.md"
            if skill_md.is_file():
                yield bare, skill_md
            for extra in sorted(adv_dir.glob("memory/*.md")):
                yield bare, extra
            for extra in sorted(adv_dir.glob("references/**/*.md")):
                yield bare, extra


def agent_memory_dir() -> Path: return repo_root() / "agent-memory"
def advisors_memory_dir() -> Path: return agent_memory_dir() / "advisors"
def executors_memory_dir() -> Path: return agent_memory_dir() / "executors"
def briefings_dir() -> Path: return advisors_memory_dir() / "briefings"
def sessions_dir() -> Path: return advisors_memory_dir() / "sessions"
def decisions_dir() -> Path: return advisors_memory_dir() / "decisions"
def mentions_dir() -> Path: return advisors_memory_dir() / "mentions"
def feedback_dir() -> Path: return advisors_memory_dir() / "feedback"
def feedback_archive_dir() -> Path: return advisors_memory_dir() / "feedback" / "archive"
def hot_md_path() -> Path: return agent_memory_dir() / "hot.md"
def executor_memory_dir(eid: str) -> Path: return executors_memory_dir() / eid
def handoffs_dir() -> Path: return repo_root() / "ops" / "handoffs"
def gh_cache_dir() -> Path: return agent_memory_dir() / "gh-cache"
def git_cache_dir() -> Path: return agent_memory_dir() / "git-cache"
def run_log_dir() -> Path:
    # CONCLAVE_RUN_LOG_DIR overrides the DATA-root location so the test harness can
    # contain observability writes to tmp instead of the real repo run-log (#53).
    override = os.environ.get("CONCLAVE_RUN_LOG_DIR")
    return Path(override) if override else agent_memory_dir() / "run-log"
def skills_dir() -> Path: return engine_root() / "skills"
def contracts_dir() -> Path: return engine_root() / "contracts"
def forge_dir() -> Path: return engine_root().parent / "skills" / "forge-operations"
def forge_references_dir() -> Path: return forge_dir() / "references"


def forge_templates_dir() -> Path: return forge_references_dir() / "templates"
def templates_dir() -> Path: return forge_templates_dir()


def snapshot_path_for_advisor(cache_type: str, advisor_id: str) -> Path:
    if cache_type == "gh":
        base = gh_cache_dir()
    elif cache_type == "git":
        base = git_cache_dir()
    else:
        raise ValueError(
            f'snapshot_path_for_advisor: invalid cache_type "{cache_type}" (must be gh or git)')
    return base / f"{advisor_id}.md"


def ensure_dir(d: Path | str) -> Path:
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p
