"""enginelib/router.py — scaffold the per-advisor /conclave-<id> invocation router.

Writes a project-side .claude/skills/conclave-<id>/SKILL.md from the advisor-router
template so every advisor is invocable as /conclave-<id> (live-reloaded, survives
plugin updates). I/O-free core: reads template, writes file; no print/argparse/exit.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from enginelib import advisors, paths, snapshot

# The placeholder a fresh mint carries; `engine model bump` replaces it.
_MINTED_VERSION = "0.0.0"


def _is_enriched(text: str) -> bool:
    """True if a wrapper carries post-mint enrichment worth preserving (#58).

    Two signals, and neither is "has a forge: block" any more. Every minted router
    now carries one — forge's did not, which is why `engine model bump` silently
    skipped the one advisor shipped in every instance ("skip-no-forge"). Presence
    of the block therefore no longer distinguishes anything.

    What still does: a hire-time markdown section (`## Scope` / `## Skill Protocol`
    / `## Domain Chains`), or a model-version that has been BUMPED off the minted
    placeholder. The second replaces exactly the protection the first signal used
    to provide — without it, re-scaffolding would quietly reset a stamped advisor
    to 0.0.0.
    """
    if "\n## " in text:
        return True
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("model-version:"):
            return stripped[len("model-version:"):].strip() != _MINTED_VERSION
    return False


def scaffold_router(
    advisor_id: str, *, skills_root: Path | None = None, force: bool = False
) -> dict:
    """Render advisor-router.md to <skills_root>/conclave-<id>/SKILL.md.

    skills_root defaults to paths.project_skills_dir(). Idempotent for bare
    first-mint stubs (overwrites). Refuses to clobber an *enriched* wrapper
    (#58) unless force=True — returns {..., "skipped": "enriched"} instead.
    Returns {"id": advisor_id, "skill": <path str>}. Raises ValueError on bad id.
    """
    advisors.validate_advisor_id(advisor_id)
    root = skills_root if skills_root is not None else paths.project_skills_dir()
    skill_dir = root / f"conclave-{advisor_id}"
    skill_file = skill_dir / "SKILL.md"
    # Refuse-to-overwrite guard (#58): a blind re-render wipes hire-time
    # enrichment + the forge: block. Bare stubs carry neither, so re-minting
    # them stays idempotent; only enriched wrappers are protected.
    if (
        not force
        and skill_file.exists()
        and _is_enriched(skill_file.read_text(encoding="utf-8"))
    ):
        return {"id": advisor_id, "skill": str(skill_file), "skipped": "enriched"}
    template = (paths.templates_dir() / "advisor-router.md").read_text(encoding="utf-8")
    rendered = template.replace("${ID}", advisor_id)
    skill_dir.mkdir(parents=True, exist_ok=True)
    snapshot.snapshot_write(skill_file, _insert_forge_block(rendered, advisor_id))
    return {"id": advisor_id, "skill": str(skill_file)}


def _insert_forge_block(text: str, advisor_id: str) -> str:
    """Insert the `forge:` model-version block before the frontmatter's closing fence.

    Line-based, not YAML-parsed: the description is a `|` block scalar and a naive
    parse would be brittle. Falls back to the original text when no closing fence is
    found — a minted wrapper always has one.

    Minting this HERE rather than in `advisor.create` is what makes forge ordinary:
    `create` covers hired advisors, but forge is provisioned by `scaffold-router`
    alone, so the block — and with it `engine model bump` — never reached it.
    """
    block = (
        "forge:\n"
        f"  model-version: {_MINTED_VERSION}\n"
        "  hired-by: forge-chro\n"
        f"  hired-at: {date.today().isoformat()}\n"
    )
    lines = text.splitlines(keepends=True)
    fences = 0
    for i, ln in enumerate(lines):
        if ln.rstrip("\r\n") == "---":
            fences += 1
            if fences == 2:
                lines.insert(i, block)
                return "".join(lines)
    return text
