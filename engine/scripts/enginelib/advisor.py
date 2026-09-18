"""enginelib/advisor.py — flat advisor scaffold (spec 099 Wave 3C.5).

DECISION 1 — Flat-only: legacy skill-dir mode dropped entirely. Always produces
a single agent-def at agents/<id>.md with internal `name: <id>` (no team. prefix).

DECISION 2 — agents_dir: the DATA root's .claude/agents, always. The project side
(CLAUDE_PROJECT_DIR/.claude, 098 D-6) gets a relative symlink per item instead.
REVISED by #134: this used to resolve to the project side and write a real file
there, which is a place CODE gitignores *because* the file is meant to be in DATA —
so a hired advisor was committed to neither repository. On a colocated instance the
two roots are the same directory, there is nothing to point at, and the real file
stays put.

DECISION 3 — version/language/context reads dropped (YAGNI): flat template has no
${MODEL_VERSION}, ${HIRE_VERSION}, ${FORGE_VERSION}, ${TEAM_LANGUAGE}, or
${PROJECT_CONTEXT_PATH} placeholders.

DECISION 4 — str.replace not sed: fixes 097 C-4 & escaping bug for free; no
_sed_rhs escaping needed.

I/O-free core: reads and writes files; no print, no argparse, no sys.exit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
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

    # 4. agents_dir resolution. The REAL file goes to DATA (spec 103 §4) and the
    #    project side gets a symlink in step 8.6 — see _link_into_project. Writing it
    #    project-side, as this did until #134, put a hired advisor in NEITHER repo:
    #    CODE gitignores `.claude/agents/` precisely because the file is supposed to be
    #    in DATA, and it was not.
    agents_dir = paths.data_agents_dir()
    agent_file = agents_dir / f"{id_}.md"

    # 5. Collision guards — DATA first, then the project-side link paths. Both run
    #    BEFORE anything is written. A refusal that fires at link time (step 8.6) has
    #    already scaffolded DATA, so "move the CODE file into DATA and re-run" sends
    #    the operator at an occupied path and the re-run they were asked for dies on
    #    this very guard.
    if agent_file.exists():
        raise FileExistsError(f"already exists: {agent_file}")
    project_links = [
        paths.project_agents_dir() / f"{id_}.md",
        paths.advisor_skill_dir(id_, paths.project_skills_dir()),
    ]
    if paths.is_split_layout():
        for link in project_links:
            _refuse_if_occupied(link)

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
        # `emoji:` is a real key in the template since #134. It was substituted here
        # for as long as the template had nowhere to put it — a no-op `.replace()`
        # reads exactly like one that works, so the value reached the file only as
        # prose inside the generated description while seven shipped EXECUTOR defs
        # carried the key and no advisor def did.
        .replace("${EMOJI}", emoji)
        # ${TONE} / ${TONE_HINT} were dead the same way and stay removed: `tone` is
        # live — stub_description() spends it — but no reader anywhere asks an
        # agent-def for a `tone:` key, and a template key nothing reads is a second
        # place for this pair to drift.
        .replace("${DESCRIPTION}", frontmatter.as_block(description))
    )
    snapshot.snapshot_write(agent_file, rendered)

    # 8. Scaffold the /conclave-<id> invocation router alongside the agent-def
    # (agents_dir.parent == the DATA .claude/, so .claude/skills stays consistent
    # with the resolved base without re-resolving env — the two move together).
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
    # The chain below was lowercase-only, and the template's identity card is written
    # in title case — so every row of it shipped verbatim and the first briefing a new
    # consumer opened read `| **Name** | {{Name}} |` (#118). The template claimed a
    # post-scaffold lint caught this; none existed, for as long as the claim did.
    #
    # The card is the SCAFFOLD's half: create() is handed every value in it. The prose
    # prompts are the operator's and must survive — a blanket
    # `re.sub(r"\{\{[^}]*\}\}", ...)` (what create_executor does, legitimately, for a
    # template with no well) would green the card and erase the 4-axis voice well that
    # hire.md §3a.5 greps to validate a hire. Both directions are gated by
    # tests/test_minted_persona_identity_is_filled.py.
    #
    # `Tier` was a three-way menu — this template is `applies-to: advisors` and
    # executors take executor-identity-card.md, so it was a choice with one option
    # left for a reader to make in a file nobody edits.
    personality = (
        personality
        .replace("{{advisor}}", name)
        .replace("{{name}}", name)
        .replace("{{emoji}}", emoji)
        .replace("{{role}}", opts.role)
        .replace("{{Name}}", name)
        .replace("{{Emoji}}", emoji)
        .replace("{{Role}}", opts.role)
        .replace("{{Color from palette}}", opts.color)
        .replace("{{Tier}}", "Advisor")
        # Same fact, same call as the `hired-at:` stamp router.scaffold_router writes
        # for the SKILL.md a few lines above — kept identical so the two surfaces of
        # one hire cannot read as two dates.
        .replace("{{YYYY-MM-DD}}", date.today().isoformat())
        .replace("${PROJECT_NAME}", project_name)
    )
    snapshot.snapshot_write(skill_file.parent / "memory" / "personality.md", personality)

    # 8.5b. Seed the briefing stub (#75). hire.md's Post-hire step asserts as
    # established fact that "the scaffold left the briefing holding the
    # AWAITING_FIRST_LAUNCH sentinel" — but briefing-awaiting.md existed in the
    # template set with nothing copying it, so the sentinel was never on disk.
    #
    # The stub is a LABEL for a human opening the file, not the first-launch detector:
    # #169 established that nothing ever read it and that nothing could, since
    # session_init rebuilds the briefing on every start. Detection lives in
    # lifecycle/session_init.py::_detect_first_launch and reads the session ledger.
    # ${CLAUDE_PLUGIN_ROOT} stays literal: it is a path the reader resolves at
    # runtime, not a build-time placeholder.
    briefing_stub = (
        paths.templates_dir() / "briefing-awaiting.md"
    ).read_text(encoding="utf-8").replace("${ID}", id_)
    snapshot.snapshot_write(paths.briefings_dir() / f"{id_}.md", briefing_stub)

    # 8.6. Publish the advisor to the CODE checkout as symlinks (#134). Both surfaces
    # are loaded by the harness from the project side, so without this step a hire is
    # invisible to the tool that has to dispatch it — and with a real file instead of a
    # link it is invisible to both repositories.
    #
    # Per-FILE for agents and per-DIR for skills, deliberately: a whole-directory
    # `.claude/agents` symlink is undocumented and reported broken in Claude Code,
    # while a skills entry pointing at a directory elsewhere on disk is the documented
    # pattern (#30's layout table).
    for real, link in (
        (agent_file, project_links[0]),
        (skill_file.parent, project_links[1]),
    ):
        _link_into_project(real, link)

    # 9. Return JSON-serialisable result
    return {"id": id_, "agent": str(agent_file), "router": str(skill_file)}


def _refuse_if_occupied(link: Path) -> None:
    """Refuse when something that is not ours already sits at a project-side link path.

    Called from the collision-guard step, before a single byte is written, because the
    thing this protects is a REAL FILE in the CODE tree — the pre-#134 shape. It is
    gitignored there and absent from DATA, so it is the only copy of whatever a hire or
    a hand-edit put in it. The rule against quiet removal binds hardest exactly where
    the file looks like leftover junk.

    A symlink is left to _link_into_project: pointing at the right place is a no-op,
    pointing elsewhere is its own error with its own message.
    """
    if link.is_symlink() or not link.exists():
        return
    raise FileExistsError(
        f"{link} is a real file where a symlink into the DATA repo belongs. CODE "
        "gitignores this path and DATA does not have it, so it is the only copy — "
        "move it into the DATA root and re-run rather than letting this overwrite it."
    )


def _link_into_project(real: Path, link: Path) -> None:
    """Point *link* at *real* with a RELATIVE target. No-op on a colocated instance.

    Relative because an absolute target embeds the operator's home directory (#83) and
    dies the moment the checkout is cloned, moved, or opened as a worktree.
    """
    if not paths.is_split_layout():
        return
    if link.is_symlink():
        if link.resolve() == real.resolve():
            return
        raise FileExistsError(
            f"{link} already links elsewhere: {os.readlink(link)} (expected {real})"
        )
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(
        os.path.relpath(real, link.parent),
        target_is_directory=real.is_dir(),
    )


