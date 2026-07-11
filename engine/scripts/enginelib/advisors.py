"""advisors.py — canonical advisor inventory + validation helpers.
Port of lib/advisors.sh.

Canonical advisor name = team.<name>/SKILL.md slug minus the "team." prefix.
Lifecycle skills are infrastructure, not advisors, and are excluded.
"""
import os
from pathlib import Path

from enginelib.paths import (
    iter_advisor_skills,
    plugin_agents_dir,
    project_agents_dir,
    skills_dir,
)

# Keep in sync with lib/advisors.sh and team.forge/SKILL.md.
_LIFECYCLE_SKILLS = frozenset({
    "start", "processing", "done", "handoff", "forge",
    "hire", "retro", "feedback", "feedback-triage",
})


def _is_lifecycle(name: str) -> bool:
    return name in _LIFECYCLE_SKILLS


def _strip_team(name: str) -> str:
    return name[len("team."):] if name.startswith("team.") else name


def _agent_ids(agents_dir: Path) -> set[str]:
    """Advisor ids from <agents_dir>/*.md: strip a leading team., drop exec-*."""
    ids: set[str] = set()
    if not agents_dir.is_dir():
        return ids
    for md in agents_dir.glob("*.md"):
        stem = _strip_team(md.stem)
        if stem.startswith("exec-"):
            continue
        ids.add(stem)
    return ids


def canonical_advisors() -> list[str]:
    """Sorted union of advisor ids across three sources, team.-normalized, deduped:
    legacy skills_dir()/team.*/SKILL.md (minus lifecycle), plugin agents/*.md,
    project .claude/agents/*.md (both minus exec-*). forge is included via agents."""
    names: set[str] = set()
    # Skills-glob half: dual-read conclave-<id> (current) + team.<id> (legacy) via
    # the shared #54 discovery helper, which yields bare ids deduped across both.
    for bare, _skill_md in iter_advisor_skills(skills_dir()):
        if not _is_lifecycle(bare):
            names.add(bare)
    names |= _agent_ids(plugin_agents_dir())
    # Project hired agent-defs: only when CLAUDE_PROJECT_DIR is set explicitly.
    # In dev/test the repo_root() ops+.claude heuristic can escape a worktree
    # into a sibling checkout; skip rather than risk unioning unrelated agents.
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        names |= _agent_ids(project_agents_dir())
    return sorted(names)


def is_canonical_advisor(name: str = "", *, allow_lifecycle: bool = False) -> bool:
    """Return True if name is a canonical advisor.

    Special case: if allow_lifecycle is True and name == "lifecycle" (the
    literal sentinel), return True without checking the skills directory.
    Empty name always returns False.
    """
    if not name:
        return False
    if allow_lifecycle and name == "lifecycle":
        return True
    return name in canonical_advisors()


# Forge is a META-advisor: a valid lifecycle target but not a domain advisor,
# so it is excluded from registry-driven enumeration (Forge invariant #7).
_META_ADVISORS = frozenset({"forge"})


def _agents_dir_for(root: Path) -> Path:
    """Resolve <project>/.claude/agents for an explicit DATA/project root.

    CLAUDE_PROJECT_DIR wins; else a `.conclave` DATA root's project is its parent
    (agents live in the SIBLING root.parent/.claude/agents); else root is already
    project-like (in-repo / test layout) and agents live in <root>/.claude/agents.
    """
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        base = Path(project)
    elif root.name == ".conclave":
        base = root.parent
    else:
        base = root
    return base / ".claude" / "agents"


def known_advisors(root: Path) -> set[str]:
    """Registry-driven advisor discovery from an explicit root — never hardcoded.

    Globs `_agents_dir_for(root)/*.md`; slug = file stem. Excludes forge (META)
    and exec-* (executors). Empty-safe: a missing agents dir yields an empty set,
    never a CANONICAL_ADVISORS fallthrough. Resolves the .conclave-sibling layout
    without requiring CLAUDE_PROJECT_DIR — the pattern session_init already uses.
    """
    advisors: set[str] = set()
    for agent_file in _agents_dir_for(root).glob("*.md"):
        stem = agent_file.stem
        if stem in _META_ADVISORS or stem.startswith("exec-"):
            continue
        advisors.add(stem)
    return advisors
