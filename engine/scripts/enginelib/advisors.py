"""advisors.py — canonical advisor inventory + validation helpers.
Port of lib/advisors.sh.

Canonical advisor name = team.<name>/SKILL.md slug minus the "team." prefix.
Lifecycle skills are infrastructure, not advisors, and are excluded.
"""
import os
import re
from pathlib import Path

from enginelib.paths import (
    advisor_skill_dir,
    forge_dir,
    iter_advisor_skills,
    plugin_agents_dir,
    project_agents_dir,
    project_skills_dir,
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
    """Advisor ids from <agents_dir>/*.md: strip a leading team., drop executors.

    Executors come in two spellings — `exec-<name>-<role>` and the pre-standard
    dotted form. Dropping only the first counted every executor on an instance
    that predates the hyphen standard as an advisor.

    `is_file()` follows the link: the project's agents dir is a symlink layer
    over the DATA tree, so retiring an advisor can leave a dangling link behind.
    """
    ids: set[str] = set()
    if not agents_dir.is_dir():
        return ids
    for md in agents_dir.glob("*.md"):
        if not md.is_file():
            continue
        stem = _strip_team(md.stem)
        if stem.startswith(("exec-", "exec.")):
            continue
        ids.add(stem)
    return ids


# The closed vocabulary of advisor role slugs. An advisor id is `<name>-<role>`,
# mirroring the executors' `exec-<name>-<role>` and its exactly-3-segment gate.
#
# The rule that admits a slug: it must name a SEAT ACCOUNTABLE FOR AN OUTCOME the
# product is judged on — revenue, security posture, architecture, the privacy
# promise — not a FUNCTION THAT PRODUCES AN ARTIFACT when dispatched. Two
# mechanical corollaries make that checkable rather than arguable: an advisor role
# is standing (it persists between sessions and accumulates memory) where an
# executor role is dispatched; and an advisor role must be an unambiguous executive
# title a person can actually hold. `eng` fails all three — nobody holds the title
# "Eng", and its accountability sentence collapses to "produces code", which is the
# executor role `dev`.
#
# Ambiguous acronyms are excluded rather than arbitrated: `cdo` (Data vs Digital)
# has no dominant reading, so the data seat is `cdao`; `cco` has four; `cso` three,
# so security is `ciso`. Where one reading DOES dominate in software the short slug
# is kept and the others get longer established forms: `cpo` is Product, privacy is
# `cdpo`, people is `chro`; `cro` is Revenue.
#
# `cxo` was excluded with those three and is readmitted (2026-08-14). Its collision
# is of a different kind: each of `cdo`/`cco`/`cso` collides with ANOTHER REAL SEAT,
# so picking one decides an accountability by acronym. "CxO" is a metasyntactic
# placeholder for any C-level officer — nobody holds the title "Chief x Officer" —
# so the experience seat keeps the short slug without arbitrating between seats.
#
# `chro` is the seat forge holds: it hires advisors, evolves their personalities and
# responsibilities, and audits the roster for drift. Under the operator's ruling
# that forge is an ordinary advisor that merely ships pre-installed, the roster IS
# the organisation it manages, so the people seat is not vacuous here.
ADVISOR_ROLES: frozenset[str] = frozenset({
    "ceo",    # strategy, prioritisation, "should we build this at all"
    "coo",    # delivery cadence, process, operational execution
    "cto",    # architecture, engineering direction, technical risk, performance
    "cpo",    # product vision, roadmap, scope, UX
    "cxo",    # the display contract — what a human-facing surface shows and how
    "cmo",    # brand, positioning, demand generation, content/SEO
    "cro",    # monetisation, pricing, the acquisition→revenue funnel
    "cfo",    # unit economics, budget, runway
    "ciso",   # threat model, vulnerabilities, security posture
    "cdpo",   # the promise made about personal data — consent, retention, trust
    "cdao",   # data governance, metrics, measurement, experimentation
    "clo",    # legal, licensing, regulatory compliance, ToS/IP
    "chro",   # the roster itself — hiring, evolution, drift
})

_ADVISOR_ID_RE = re.compile(rf"^[a-z0-9]+-(?:{'|'.join(sorted(ADVISOR_ROLES))})$")


def validate_advisor_id(advisor_id: str) -> None:
    """Raise ValueError unless *advisor_id* is `<name>-<role>` with a vocabulary role.

    Exactly two segments — the persona name carries no hyphen. That mirrors the
    executor gate's exactly-three; letting `mary-jane-cto` through here while
    `exec-mary-jane-dev` is rejected would make two rules meant to mirror each
    other disagree.

    A shape-only check would not do the job this exists for: `engineering-data`
    and `growth-monetization` have two segments each and are still two domains
    with no persona. Only the closed vocabulary separates them from `vera-cto`.
    """
    if advisor_id and _ADVISOR_ID_RE.fullmatch(advisor_id):
        return
    roles = ", ".join(sorted(ADVISOR_ROLES))
    raise ValueError(
        f"invalid advisor id: {advisor_id!r}. An advisor id is <name>-<role>: a persona "
        f"name with no hyphen, then one role from the closed vocabulary.\n"
        f"  roles: {roles}\n"
        f"Executor roles (dev, test, rank, research, critic, judge) are NOT advisor "
        f"roles — they name a function that produces an artifact, not a seat "
        f"accountable for an outcome."
    )


def is_valid_advisor_id(advisor_id: str) -> bool:
    """Non-raising twin of `validate_advisor_id`, for audits that report rather than refuse."""
    return bool(advisor_id) and bool(_ADVISOR_ID_RE.fullmatch(advisor_id))


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
META_ADVISORS = frozenset({"forge-chro"})


def personality_path(advisor_id: str, skills_base: Path | None = None) -> Path:
    """Where to READ *advisor_id*'s personality.md from.

    A hired advisor's persona is instance data: `advisor create` mints the router
    into the project skills dir and hire-time enrichment writes the persona beside
    it. A META advisor's is not. Forge ships with the engine under the SKILL's name
    (`skills/forge-operations/memory/personality.md`), not the advisor's id, and no
    instance ever writes a `conclave-<meta-id>/memory/personality.md` — so
    anchoring both kinds on the project dir asked for a file nothing creates, and
    every consumer's Forge briefing rendered the 'not yet written' placeholder.

    The project copy wins whenever it exists, so an instance that enriches its own
    Forge is never overridden by the shipped default, and a domain advisor without
    a persona still resolves to its own empty path — inheriting Forge's voice would
    be worse than an honest placeholder. When neither exists the project path is
    returned, which is also the right answer for a caller about to write one.

    This is a read-side resolver only; `advisor create` still writes beside the
    router it just minted.
    """
    base = skills_base if skills_base is not None else project_skills_dir()
    own = (
        advisor_skill_dir(advisor_id, base, artifact="memory/personality.md")
        / "memory" / "personality.md"
    )
    if own.is_file() or advisor_id not in META_ADVISORS:
        return own
    shipped = forge_dir() / "memory" / "personality.md"
    return shipped if shipped.is_file() else own


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
