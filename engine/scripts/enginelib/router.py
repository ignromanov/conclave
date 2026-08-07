"""enginelib/router.py — scaffold the per-advisor /conclave-<id> invocation router.

Writes a project-side .claude/skills/conclave-<id>/SKILL.md from the advisor-router
template so every advisor is invocable as /conclave-<id> (live-reloaded, survives
plugin updates). I/O-free core: reads template, writes file; no print/argparse/exit.
"""
from __future__ import annotations

from pathlib import Path

from enginelib import advisors, paths, snapshot


def _is_enriched(text: str) -> bool:
    """True if a wrapper carries post-mint enrichment worth preserving (#58).

    A freshly-minted router has neither a `forge:` frontmatter block nor any
    markdown section heading — the hire-time enrichment adds both (`forge:`
    model-version block + `## Scope`/`## Skill Protocol`/`## Domain Chains`).
    Either signal marks the wrapper as unsafe to blind-overwrite.
    """
    return "\nforge:" in text or "\n## " in text


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
    snapshot.snapshot_write(skill_file, rendered)
    return {"id": advisor_id, "skill": str(skill_file)}
