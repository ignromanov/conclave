"""enginelib/audit/phantom_skills.py — advisor phantom-skill scanner (#3).

I/O-free: no print / argparse / sys.exit. Returns Findings(crit=[], warn=[...]).

Scans the advisor-*authored surface* — each non-lifecycle advisor's SKILL.md +
memory/*.md + references/**/*.md (both `conclave-` and `team.` layouts), plus agent
defs — and flags backtick references to skills/advisors that do not resolve.

Detection is shape-graduated to keep the widened scope from drowning in false
positives (the ~80% under-report of the top-level-only scanner is fixed by widening;
the false-positive flood a naive widen produces is fixed by the cue gate):

  * namespaced  `plugin:skill`      → always a skill ref; verify via skill.verify.
  * prefixed    `team.x`/`conclave-x` → an advisor/lifecycle ref; resolve against the
                                        discovered roster (skill.verify is blind to
                                        project advisor skills, so it can't judge these).
  * bare kebab  `find-skills`        → ambiguous (could be any kebab noun); treated as
                                        a skill ref ONLY inside an invocation context
                                        (a skill-list bullet, an invocation cue word,
                                        or immediately followed by "skill"). A bare id
                                        that matches a known advisor is never a phantom.
"""
from __future__ import annotations

import re
from pathlib import Path

from enginelib import skill
from enginelib.audit import Findings
from enginelib.paths import iter_advisor_authored_files

# Bare advisor ids (prefix-agnostic) — the #54 helper yields bare ids.
_LIFECYCLE = frozenset({
    "start", "processing", "done", "handoff",
    "forge", "hire", "retro", "feedback", "feedback-triage",
})

# Backtick-wrapped token starting with a lowercase letter.
_BACKTICK_RE = re.compile(r"`([a-z][a-z0-9:.\-]+)`")

# Legitimate skill-name forms:
#   1. plugin:skill   e.g. superpowers:brainstorming
#   2. team.<name>    e.g. team.kai-cto
#   3. kebab-case     at least one hyphen, e.g. find-skills
_SKILL_RE = re.compile(
    r"^([a-z][a-z0-9-]+:[a-z][a-z0-9-]+|team\.[a-z][a-z0-9-]+|[a-z0-9]+(-[a-z0-9]+)+)$"
)

# Invocation cue words (skill about to be loaded/routed/used). Matched in the ~30
# chars preceding a bare-kebab token, or as a trailing "skill(s)" after it.
_CUE_RE = re.compile(
    r"\b(use|uses|using|invoke|invokes|invoking|load|loads|loading|run|runs|running"
    r"|chain|chains|consult|consults|route|routes|replacing|via)\b|→",
    re.IGNORECASE,
)
_TRAILING_SKILL_RE = re.compile(r"\s+skills?\b", re.IGNORECASE)


def _is_bullet_skill_ref(line: str, m: re.Match) -> bool:
    """True when the token is the leading backtick of a list bullet (Toolbox tier),
    excluding `x` → glossary/mapping bullets (which are domain tags, not skills)."""
    if not re.match(r"^\s*[-*]\s+$", line[: m.start()]):
        return False
    return not re.match(r"\s*→", line[m.end():])


def _refs_in_line(line: str) -> list[str]:
    """Extract skill/advisor reference tokens from one line under the graduated rule."""
    out: list[str] = []
    for m in _BACKTICK_RE.finditer(line):
        tok = m.group(1)
        if not _SKILL_RE.match(tok):
            continue
        if ":" in tok or tok.startswith(("team.", "conclave-")):
            out.append(tok)          # high-confidence shape — always a ref
            continue
        # bare kebab — require an invocation context
        pre = line[max(0, m.start() - 30): m.start()]
        if _is_bullet_skill_ref(line, m) or _CUE_RE.search(pre) or _TRAILING_SKILL_RE.match(line[m.end():]):
            out.append(tok)
    return out


def _extract_refs(text: str) -> list[str]:
    refs: set[str] = set()
    for line in text.splitlines():
        refs.update(_refs_in_line(line))
    return sorted(refs)


def _is_phantom(ref: str, known: frozenset[str]) -> bool:
    """Resolve a reference: namespaced/bare → skill.verify; prefixed → roster lookup."""
    if ":" in ref:
        return skill.verify(ref) is None
    if ref.startswith("team."):
        return ref.split(".", 1)[1] not in known
    if ref.startswith("conclave-"):
        return ref[len("conclave-"):] not in known
    if ref in known:                 # a bare advisor id, not a skill
        return False
    return skill.verify(ref) is None


def _scan(path: Path, label: str, known: frozenset[str], warn: list[str], seen: set) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for ref in _extract_refs(text):
        if _is_phantom(ref, known):
            key = (label, ref)
            if key in seen:
                continue
            seen.add(key)
            warn.append(f"{label}: references phantom skill: {ref}")


def run(skills_dir: Path, agents_dir: Path | None = None) -> Findings:
    """Scan the advisor-authored surface (+ agent defs) for phantom skill references."""
    authored = list(iter_advisor_authored_files(skills_dir))
    known = frozenset({bare for bare, _ in authored} | _LIFECYCLE)

    warn: list[str] = []
    seen: set = set()

    for bare, md in authored:
        if bare in _LIFECYCLE:
            continue
        _scan(md, bare, known, warn, seen)

    if agents_dir is not None and agents_dir.is_dir():
        for agent_md in sorted(agents_dir.glob("*.md")):
            _scan(agent_md, agent_md.stem, known, warn, seen)

    return Findings(crit=[], warn=warn)
