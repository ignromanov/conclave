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


def advisor_label(advisor: str) -> str:
    """The GitHub label for *advisor* — `advisor:<id>`, per github-issues-protocol.md.

    One function so the write side and the read side cannot drift. They did: the
    write paths labelled `advisor:kai-cto` while two read paths queried
    `advisor:kai` (`advisor.split("-")[0]`). GitHub matches labels exactly, so
    every hyphenated advisor had a permanently empty issue queue and no error
    anywhere said so.
    """
    return f"advisor:{advisor}"


def files_for_advisor(directory: Path, advisor: str, *, field: str) -> list[Path]:
    """Records under *directory* that belong to *advisor*, sorted by path.

    Ownership is read from the frontmatter *field* (`advisor:` for sessions,
    `by:` for decisions) — NOT from the filename. The glob `*-<advisor>-*.md`
    that every call site used to run answers an id change with an empty list
    instead of an error, so a rename silently emptied the reflexion buffer and
    the briefing's session list with nothing reporting a fault.

    The filename stays a FALLBACK for records written before the field existed,
    so legacy data behaves exactly as it did. A field, when present, always wins:
    a file whose name says one advisor and whose field says another belongs to
    the field's advisor.
    """
    if not directory.is_dir():
        return []
    out: list[Path] = []
    for f in sorted(directory.glob("*.md")):
        owner = _frontmatter_value(f, field)
        if owner is None:
            if f"-{advisor}-" in f.name:
                out.append(f)
        elif owner == advisor:
            out.append(f)
    return out


def _frontmatter_value(path: Path, key: str) -> str | None:
    """The value of *key* in the first frontmatter block, or None if absent.

    Line-based on purpose — mirrors enginelib.frontmatter, and importing it here
    would be circular. The opening fence is the FIRST `---` line anywhere: some
    records (feedback) open with an HTML comment above their frontmatter.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    in_fm = False
    for line in text.splitlines():
        if line.strip() == "---":
            if in_fm:
                break
            in_fm = True
            continue
        if in_fm and line.startswith(f"{key}:"):
            return line[len(key) + 1:].strip().strip('"').strip("'")
    return None


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
    # Project hired agent-defs: only when an explicit anchor env var is set —
    # CLAUDE_PROJECT_DIR, or CONCLAVE_AI_ROOT (exported by the SessionStart
    # hook in real sessions; see #24). With neither set, the repo_root()
    # ops+.claude ancestor-walk from cwd is untrusted: in dev/test it can
    # escape a worktree into a sibling checkout, so skip rather than risk
    # unioning unrelated agents.
    if os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("CONCLAVE_AI_ROOT"):
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
META_ADVISORS = frozenset({"forge"})


def with_meta(roster: set[str]) -> set[str]:
    """*roster* plus the shipped META advisors — the set valid as a lifecycle target.

    A "may this advisor do X" gate needs roster | META; enumeration alone
    (dashboards, digests, audits) wants the roster without it. Conflating the two
    is a recurring defect class — forge, the one advisor guaranteed to exist in
    every instance, gets rejected by a gate built on enumeration (#38). Centralizes
    the union so call sites stop re-open-coding `roster | META_ADVISORS` by hand.
    """
    return roster | META_ADVISORS


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
        if stem in META_ADVISORS or stem.startswith("exec-"):
            continue
        advisors.add(stem)
    return advisors


def lifecycle_advisors(root: Path) -> set[str]:
    """The set valid as a *lifecycle target* — the hired roster plus the shipped
    META roles.

    This answers a different question from `known_advisors()`, and conflating the
    two is a live defect class: `known_advisors()` enumerates the instance's own
    domain roster (so audits and digests do not report forge as a hire), while a
    lifecycle gate asks "may this advisor run this phase". forge ships in every
    instance and is the one advisor guaranteed to exist, so a gate built on the
    enumeration rejects it. Gate on this; enumerate on `known_advisors()`.
    """
    return with_meta(known_advisors(root))
