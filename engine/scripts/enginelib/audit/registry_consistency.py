"""enginelib/audit/registry_consistency.py — port of audit-registry-consistency.sh.

I/O-free: no print/argparse/sys.exit. Returns Findings for the adapter to format.

Defect classes:
  CRIT: advisor has SKILL.md but no agents/*.md (or vice versa).
  WARN: skill advisor name not found as substring in CLAUDE.md.

Missing CLAUDE.md decision: bash `grep -q` would error under `set -e` if the file is absent.
To stay robust and faithful-in-spirit, a missing CLAUDE.md is treated as "mentions nothing"
(every skill advisor → WARN), matching the intent of the original guard.
"""
from __future__ import annotations

from pathlib import Path

from enginelib.audit import Findings
from enginelib.paths import iter_advisor_skills

# Bare advisor ids (prefix-agnostic). Both sides of the symmetry check are keyed on
# bare ids (#54): skill dirs are conclave-<id>/team.<id>, agent-defs are bare <id>.md
# (current mint) or legacy team.<id>.md — only bare ids compare across both.
_LIFECYCLE: frozenset[str] = frozenset({
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

_AGENT_PREFIXES = ("conclave-", "team.")


def _bare_agent_id(stem: str) -> str:
    for prefix in _AGENT_PREFIXES:
        if stem.startswith(prefix):
            return stem[len(prefix):]
    return stem


def run(skills_dir: Path, agents_dir: Path, claude_md: Path) -> Findings:
    crit: list[str] = []
    warn: list[str] = []

    # Build SKILL advisor set — dual-read conclave-/team. via the #54 helper (bare ids).
    skill_advisors: set[str] = set()
    if skills_dir.is_dir():
        for bare, _skill_md in iter_advisor_skills(skills_dir):
            if bare not in _LIFECYCLE:
                skill_advisors.add(bare)

    # Build AGENT advisor set — bare <id>.md (current mint) or legacy team.<id>.md,
    # normalized to bare ids; executors (exec-*) are not advisors.
    agent_advisors: set[str] = set()
    if agents_dir.is_dir():
        for p in agents_dir.glob("*.md"):
            name = _bare_agent_id(p.stem)
            if name in _LIFECYCLE or name.startswith("exec-"):
                continue
            agent_advisors.add(name)

    # CRIT: symmetry checks (sorted for deterministic output)
    for s in sorted(skill_advisors):
        if s not in agent_advisors:
            crit.append(f"{s} has skill but no agents/*.md")
    for a in sorted(agent_advisors):
        if a not in skill_advisors:
            crit.append(f"{a} in agents/ but no skill dir")

    # WARN: CLAUDE.md presence (substring match, same as bash `grep -q "$s"`)
    text = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    for s in sorted(skill_advisors):
        if s not in text:
            warn.append(f"{s} not mentioned in CLAUDE.md")

    return Findings(crit=crit, warn=warn)
