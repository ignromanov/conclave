"""enginelib/advisor.py — flat advisor scaffold (spec 099 Wave 3C.5).

DECISION 1 — Flat-only: legacy skill-dir mode dropped entirely. Always produces
a single agent-def at agents/<id>.md with internal `name: <id>` (no team. prefix).

DECISION 2 — agents_dir: CLAUDE_PROJECT_DIR/.claude/agents if env set (098 D-6
plugin target); else repo_root()/.claude/agents (data-root / dev mode).

DECISION 3 — version/language/context reads dropped (YAGNI): flat template has no
${MODEL_VERSION}, ${HIRE_VERSION}, ${FORGE_VERSION}, ${TEAM_LANGUAGE}, or
${PROJECT_CONTEXT_PATH} placeholders.

DECISION 4 — str.replace not sed: fixes 097 C-4 & escaping bug for free; no
_sed_rhs escaping needed.

I/O-free core: reads and writes files; no print, no argparse, no sys.exit.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from enginelib import advisors, frontmatter, paths, roster, router, snapshot


@dataclass
class AdvisorOpts:
    id: str
    role: str
    color: str
    name: str = ""
    emoji: str = ""
    tone: str = ""
    description: str = ""


def stub_description(emoji: str, role: str, tone: str) -> str:
    """The identity line a hire produces when nobody supplied one.

    `role` and `tone` cannot yield "what will this advisor help me with" —
    that is elicited knowledge, not a derivation, and hire.md Phase 1 already
    asks for it. This keeps create() callable without one and gives the
    description gate a recognisable stub to reject before it ships.
    """
    return f"{emoji} {role} advisor — {tone}"


def create(opts: AdvisorOpts) -> dict:
    """Scaffold a flat agent-def at agents/<id>.md.

    Returns {"id": ..., "agent": ...} on success.
    Raises ValueError on validation failure (adapter → exit 1).
    Raises FileExistsError on collision (adapter → exit 2).
    """
    # 1. Validate required fields
    if not opts.id or not opts.role or not opts.color:
        raise ValueError(
            "usage: engine advisor create --id X --role Y --color Z"
            " [--name N --emoji E --tone T]"
        )
    advisors.validate_advisor_id(opts.id)

    # 2. Defaults
    id_ = opts.id
    name = opts.name or id_  # used in personality stub (#55); flat template has no ${NAME}
    emoji = opts.emoji or "🧭"
    tone = opts.tone or "pragmatic"

    # 3. Project name from roster
    project_name = roster.roster_get("project.name") or "the project"

    # 4. agents_dir resolution (shared helper — DRY with canonical_advisors discovery)
    agents_dir = paths.project_agents_dir()
    agent_file = agents_dir / f"{id_}.md"

    # 5. Collision guard
    if agent_file.exists():
        raise FileExistsError(f"already exists: {agent_file}")

    # 6. Ensure directory
    agents_dir.mkdir(parents=True, exist_ok=True)

    # 7. Render template via str.replace (DECISION 4 — fixes 097 C-4 & escaping bug)
    description = opts.description.strip() or stub_description(emoji, opts.role, tone)
    template = (paths.templates_dir() / "agent-frontmatter.md").read_text(encoding="utf-8")
    rendered = (
        template
        .replace("${ID}", id_)
        .replace("${ROLE}", opts.role)
        .replace("${PROJECT_NAME}", project_name)
        .replace("${COLOR}", opts.color)
        .replace("${EMOJI}", emoji)
        .replace("${TONE_HINT}", tone)
        .replace("${TONE}", tone)
        .replace("${DESCRIPTION}", frontmatter.as_block(description))
    )
    snapshot.snapshot_write(agent_file, rendered)

    # 8. Scaffold the /conclave-<id> invocation router alongside the agent-def
    # (project-side; agents_dir.parent == .claude, so .claude/skills stays
    # consistent with the resolved base without re-resolving env).
    # The router and the agent-def project the SAME identity string: two surfaces,
    # one source. Passing it here (rather than letting the router re-read the file
    # it was just handed) keeps them equal by construction, which is what the
    # description gate asserts.
    router_info = router.scaffold_router(
        id_, skills_root=agents_dir.parent / "skills", description=description
    )
    skill_file = Path(router_info["skill"])

    # 8.5. Provision memory/personality.md (#55). The briefing personality_path
    # resolves to conclave-<id>/memory/personality.md; without a real file it
    # degrades to the 'not yet written' placeholder. hire.md Phase 3b enriches it.
    #
    # #75: this rendered templates/personality.md — the generic 4-section stub
    # (Voice / Thinking style / Boundaries / Relationship to product). hire.md §3a.0
    # mandates personality-template.md for the advisor tier and §3a.5 validates it by
    # grepping for the 4-axis voice well, which the generic stub scores 0 of 4 on. So
    # the protocol's own documented validation failed on every single hire.
    # create() is the ADVISOR path; executors take the executor-identity-card branch
    # and never reach here.
    personality = (
        paths.templates_dir() / "personality-template.md"
    ).read_text(encoding="utf-8")
    personality = (
        personality
        .replace("{{advisor}}", name)
        .replace("{{name}}", name)
        .replace("{{emoji}}", emoji)
        .replace("{{role}}", opts.role)
        .replace("${PROJECT_NAME}", project_name)
    )
    snapshot.snapshot_write(skill_file.parent / "memory" / "personality.md", personality)

    # 8.5b. Seed the briefing stub (#75). hire.md's Post-hire step asserts as
    # established fact that "the scaffold left the briefing holding the
    # AWAITING_FIRST_LAUNCH sentinel" — but briefing-awaiting.md existed in the
    # template set with nothing copying it, so the sentinel was never on disk and
    # first-launch detection could not fire. ${CLAUDE_PLUGIN_ROOT} stays literal:
    # it is a path the reader resolves at runtime, not a build-time placeholder.
    briefing_stub = (
        paths.templates_dir() / "briefing-awaiting.md"
    ).read_text(encoding="utf-8").replace("${ID}", id_)
    snapshot.snapshot_write(paths.briefings_dir() / f"{id_}.md", briefing_stub)

    # 9. Return JSON-serialisable result
    return {"id": id_, "agent": str(agent_file), "router": str(skill_file)}


