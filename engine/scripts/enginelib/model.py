"""enginelib/model.py — advisor model-version stamping. Port of bump-model-version.sh.

I/O-free of stdout/argparse/sys.exit. File read/write only (via snapshot_write).
"""
from __future__ import annotations

from pathlib import Path

from enginelib.paths import advisor_skill_dir
from enginelib.snapshot import snapshot_write

# BARE lifecycle skill ids (prefix-agnostic; #48). The .sh used exactly these 7 (NOT
# the canonical 9-entry set — feedback/feedback-triage, if present, are encountered by
# --all, checked for a forge: block, and skip with "skip-no-forge" rather than being
# silently excluded, matching the original .sh behavior exactly).
_LIFECYCLE_SKILLS: frozenset[str] = frozenset({
    "start",
    "processing",
    "done",
    "handoff",
    "forge",
    "hire",
    "retro",
})

# Advisor SKILL-dir prefixes tolerated during the #48 migration (conclave- canonical).
_ADVISOR_PREFIXES = ("conclave-", "team.")


def current_standard(forge_ref: Path) -> str:
    """Parse `## Current standard: X.Y.Z` from agent-model-version.md.

    Replicates: grep -E '^## Current standard:' ... | awk '{print $4}' | head -1
    Field 4 is 1-indexed awk, so 0-indexed Python split()[3].
    """
    for line in Path(forge_ref).read_text(encoding="utf-8").splitlines():
        if line.startswith("## Current standard:"):
            return line.split()[3]
    raise ValueError(f"current_standard: no '## Current standard:' line in {forge_ref}")


def _rewrite_forge_block(content: str, standard: str, set_all: bool) -> str:
    """Rewrite model-version (and optionally last-evolve) in the forge: block.

    Tracks in_fm / in_forge state; exits forge block when a top-level non-forge:
    key is seen inside frontmatter.

    `hired-by` is an ACTOR (e.g. `forge`), not a version — it is a creation fact
    and is never version-stamped, even under set_all. (feedback 240857/i1: the
    original awk port rewrote `hired-by: forge` → `hired-by: <version>`.)
    """
    lines = content.splitlines(keepends=True)
    out: list[str] = []
    in_fm = False
    in_forge = False

    for line in lines:
        bare = line.rstrip("\n").rstrip("\r")

        # Rule: ^---$ → toggle fm block, always print
        if bare == "---":
            in_fm = not in_fm
            out.append(line)
            continue

        # Rule: inside fm, line starts with forge: → enter forge block, print
        if in_fm and bare.startswith("forge:"):
            in_forge = True
            out.append(line)
            continue

        # Rules: inside forge block, stamp the three versioned fields
        if in_forge and bare.startswith("  model-version:"):
            out.append(f"  model-version: {standard}\n")
            continue
        if in_forge and bare.startswith("  hired-by:"):
            # hired-by is an actor, not a version — always preserve it.
            out.append(line)
            continue
        if in_forge and bare.startswith("  last-evolve:"):
            out.append(f"  last-evolve: {standard}\n" if set_all else line)
            continue

        # Rule: inside fm, non-space, non-forge: key → exit forge block (no `next`; falls through)
        if in_fm and bare and bare[0] != " " and not bare.startswith("forge:"):
            in_forge = False

        out.append(line)

    return "".join(out)


def bump(
    target: str,
    *,
    set_all: bool,
    dry_run: bool,
    skills_dir: Path,
    standard: str,
) -> list[dict]:
    """Stamp forge.model-version in advisor SKILL.md files.

    Args:
        target: single advisor id without 'team.' prefix, or "*" for all.
        set_all: if True, also stamp last-evolve (hired-by is an actor — never stamped).
        dry_run: if True, return would-bump results without writing.
        skills_dir: path to the skills directory.
        standard: the model version string to stamp.

    Returns:
        list of dicts with keys "advisor" and "action":
        "bumped" | "would-bump" | "skip-no-forge" | "missing"
    """
    if target == "*":
        ids: set[str] = set()
        for prefix in _ADVISOR_PREFIXES:
            for p in skills_dir.glob(f"{prefix}*/SKILL.md"):
                bare = p.parent.name[len(prefix):]
                if bare not in _LIFECYCLE_SKILLS:
                    ids.add(bare)
        advisors: list[str] = sorted(ids)
    else:
        advisors = [target]

    results: list[dict] = []
    for a in advisors:
        # a is a BARE id; resolve its SKILL dir tolerating both layouts (#48).
        skill_file = advisor_skill_dir(a, skills_dir) / "SKILL.md"

        if not skill_file.is_file():
            results.append({"advisor": a, "action": "missing"})
            continue

        content = skill_file.read_text(encoding="utf-8")
        if not any(ln.startswith("forge:") for ln in content.splitlines()):
            results.append({"advisor": a, "action": "skip-no-forge"})
            continue

        if dry_run:
            results.append({"advisor": a, "action": "would-bump"})
            continue

        new_content = _rewrite_forge_block(content, standard, set_all)
        snapshot_write(skill_file, new_content)
        results.append({"advisor": a, "action": "bumped"})

    return results
