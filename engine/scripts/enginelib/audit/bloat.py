"""enginelib/audit/bloat.py — port of audit-bloat.sh.

I/O-free: no print/argparse/sys.exit. Returns Findings for the adapter to format.

Line-count caps (WARN over cap, CRIT over 2× cap).
wc -l semantics: count b"\\n" bytes, not len(splitlines()).
"""
from __future__ import annotations

from pathlib import Path

from enginelib.audit import Findings
from enginelib.paths import forge_dir, forge_references_dir, iter_advisor_skills

CAP_ADVISOR_SKILL = 150
CAP_BRIEFING = 500
CAP_ROUTER = 150
CAP_PROTOCOL = 220
CAP_ASPECT = 140

# Bare advisor ids (prefix-agnostic) — the #54 discovery helper yields bare ids,
# so lifecycle/exempt membership is tested prefix-free (conclave-<id> or team.<id>).
LIFECYCLE_SKILLS: frozenset[str] = frozenset({
    "start",
    "processing",
    "done",
    "handoff",
    "forge",
    "hire",
    "retro",
    "feedback",
    "feedback-triage",
})

BLOAT_EXEMPT_ADVISOR_SKILL: frozenset[str] = frozenset({"quorum"})


def run(
    skills_dir: Path,
    briefings_dir: Path,
    forge_refs: Path | None = None,
    forge_skill: Path | None = None,
) -> Findings:
    if forge_refs is None:
        forge_refs = forge_references_dir()
    if forge_skill is None:
        forge_skill = forge_dir() / "SKILL.md"

    crit: list[str] = []
    warn: list[str] = []

    def check(file: Path, cap: int, label: str) -> None:
        if not file.is_file():
            return
        lines = file.read_bytes().count(b"\n")
        if lines > cap * 2:
            crit.append(f"{label} {file} = {lines} lines (cap {cap})")
        elif lines > cap:
            warn.append(f"{label} {file} = {lines} lines (cap {cap})")

    # Step 1: Advisor SKILL.md — dual-read conclave-/team. (#54), skip lifecycle
    # and bloat-exempt advisors by bare id.
    for bare, p in iter_advisor_skills(skills_dir):
        if bare in LIFECYCLE_SKILLS:
            continue
        if bare not in BLOAT_EXEMPT_ADVISOR_SKILL:
            check(p, CAP_ADVISOR_SKILL, "advisor-skill")

    # Step 2: Shared advisor-memory briefings (spec 051).
    if briefings_dir.is_dir():
        for p in sorted(briefings_dir.glob("*.md")):
            check(p, CAP_BRIEFING, "briefing")

    # Step 3: Forge router (forge-operations/SKILL.md; excluded from step 1's team.* glob).
    check(forge_skill, CAP_ROUTER, "forge-router")

    # Step 4: Forge protocols.
    protocols_dir = forge_refs / "protocols"
    if protocols_dir.is_dir():
        for p in sorted(protocols_dir.glob("*.md")):
            check(p, CAP_PROTOCOL, "protocol")

    # Step 5: Forge aspects.
    aspects_dir = forge_refs / "aspects"
    if aspects_dir.is_dir():
        for p in sorted(aspects_dir.glob("*.md")):
            check(p, CAP_ASPECT, "aspect")

    return Findings(crit=crit, warn=warn)
