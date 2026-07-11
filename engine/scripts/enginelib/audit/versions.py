"""enginelib/audit/versions.py — port of audit-versions.sh.

I/O-free: no print/argparse/sys.exit. Returns VersionsReport for the adapter to format.

Compares each advisor's forge.model-version to the current standard from
team.forge/references/agent-model-version.md. The forge-block fm-gate mirrors
the bash awk: /^forge:/{fm=1} fm && /^  model-version:/{print $2; exit}.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from enginelib.paths import iter_advisor_skills


@dataclass
class VersionsReport:
    standard: str
    entries: list[str]
    crit: int
    warn: int


# Bare advisor ids (prefix-agnostic) — the #54 helper yields bare ids.
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


def run(skills_dir: Path, standard_file: Path) -> VersionsReport:
    # Parse standard: first line starting with "## Current standard:", field index 3.
    standard = ""
    if standard_file.is_file():
        for line in standard_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("## Current standard:"):
                parts = line.split()
                if len(parts) >= 4:
                    standard = parts[3]
                break

    s_parts = standard.split(".")
    std_major = s_parts[0]
    std_minor = s_parts[1] if len(s_parts) > 1 else ""

    entries: list[str] = []
    crit = 0
    warn = 0

    for bare, skill_file in iter_advisor_skills(skills_dir):  # dual-read conclave-/team. (#54)
        if bare in LIFECYCLE_SKILLS:
            continue
        advisor = skill_file.parent.name  # display keeps the full dir-name

        # Port: awk '/^forge:/{fm=1} fm && /^  model-version:/{print $2; exit}'
        # fm-gate: only read model-version from inside the forge: block.
        ver = ""
        fm = False
        for line in skill_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("forge:"):
                fm = True
            elif fm and line.startswith("  model-version:"):
                ver = line.split()[1]
                break

        if not ver:
            entries.append(f"CRIT: {advisor} has no forge.model-version stamp")
            crit += 1
            continue

        v_parts = ver.split(".")
        v_major = v_parts[0]
        v_minor = v_parts[1] if len(v_parts) > 1 else ""

        if v_major != std_major:
            entries.append(f"CRIT: {advisor} at {ver} (MAJOR gap vs {standard})")
            crit += 1
        elif v_minor != std_minor:
            entries.append(f"WARN: {advisor} at {ver} (MINOR gap vs {standard})")
            warn += 1
        else:
            entries.append(f"OK: {advisor} at {ver}")

    return VersionsReport(standard=standard, entries=entries, crit=crit, warn=warn)
