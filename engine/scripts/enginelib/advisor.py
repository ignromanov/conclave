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

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from enginelib import paths, roster, router, snapshot


@dataclass
class AdvisorOpts:
    id: str
    role: str
    color: str
    name: str = ""
    emoji: str = ""
    tone: str = ""


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
    if not re.fullmatch(r"[a-z0-9-]+", opts.id):
        raise ValueError(
            f"invalid --id: must match ^[a-z0-9-]+$ (got: {opts.id})"
        )

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
    )
    snapshot.snapshot_write(agent_file, rendered)

    # 8. Scaffold the /conclave-<id> invocation router alongside the agent-def
    # (project-side; agents_dir.parent == .claude, so .claude/skills stays
    # consistent with the resolved base without re-resolving env).
    router_info = router.scaffold_router(id_, skills_root=agents_dir.parent / "skills")
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

    # 8.6. Mint a forge: block skeleton into the wrapper frontmatter (#55) so
    # `engine model bump` has a target instead of silently skip-no-forge. The
    # model-version is a placeholder; `model bump --advisor <id>` (hire Phase 3c)
    # stamps the current standard. Only hired advisors get this — forge's own
    # router (via scaffold_forge_router) stays bare, as a meta-advisor should.
    forge_block = (
        "forge:\n"
        "  model-version: 0.0.0\n"
        "  hired-by: forge\n"
        f"  hired-at: {date.today().isoformat()}\n"
    )
    snapshot.snapshot_write(
        skill_file, _insert_forge_block(skill_file.read_text(encoding="utf-8"), forge_block)
    )

    # 9. Return JSON-serialisable result
    return {"id": id_, "agent": str(agent_file), "router": str(skill_file)}


def _insert_forge_block(text: str, block: str) -> str:
    """Insert a forge: block before the closing '---' of the wrapper frontmatter.

    Line-based (not YAML-parsed) because the description uses a '|' block scalar;
    a naive parse would be brittle. Falls back to the original text if no closing
    frontmatter fence is found (defensive — a minted wrapper always has one).
    """
    lines = text.splitlines(keepends=True)
    fences = 0
    for i, ln in enumerate(lines):
        if ln.rstrip("\r\n") == "---":
            fences += 1
            if fences == 2:
                lines.insert(i, block)
                return "".join(lines)
    return text
