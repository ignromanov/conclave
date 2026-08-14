"""enginelib/audit/routing_targets.py — resolve every routing target a shipped command names (108 P1).

I/O-free: no print / argparse / sys.exit. Reads only the files it is handed and returns
Findings(crit=[...], warn=[]).

Why this is separate from phantom_skills.py: that scanner covers the advisor-*authored* surface
and skips lifecycle skills by design (phantom_skills.py:127), and its token regex admits a dot
only in the `team.<name>` form. A routing target written `workflow.dev-lifecycle` inside
commands/start.md is therefore invisible to it twice over. The two modules cover disjoint surfaces.

Three checks, each exact. The third replaces a heuristic prototype that measured 77% noise and
was dropped rather than shipped with an exclusion list (plan-p1.md D-6):

  1. dotted   — `workflow.x` never resolves (none is authored, by decision: spec 108 D2).
                `team.x` is a NAMING debt, not a phantom — those skills exist under `conclave:x` —
                so it resolves against the lifecycle set plus the discovered roster, the same rule
                phantom_skills.py:95-98 uses. Only `team.quorum` survives that, which is what
                loop-map.md §5 measured independently.
  2. ai-root  — within the 18 surfaces this gate scans (`commands/` + `agents/`, of roughly 150
                shipped total), no path under `.ai/` may survive. That was the origin instance's
                DATA root; spec 103 moved DATA to `.conclave/`. Twelve live command instructions
                still operated on it inside this perimeter when this check was written, two of
                them in steps that run every session. Intent is broader than reach: a sweep with
                this module's own regex over the rest of the shipped tree (skills/, docs/) measures
                50 more surviving references this gate does not scan, tracked as GH#124.

  3. cells    — inside a routing table, every element of a skill chain must carry a plugin
                prefix or the `†` marker that means "unprefixed on purpose: user-level, shipped
                by no plugin, unverifiable from here". Neither ⇒ nothing can tell a real target
                from a phantom, which is how `doc-coauthoring` survived in start.md until it was
                found by hand (GH#123).
                The prototype's 77% noise came from recognising routing tables by header
                VOCABULARY, matching every schema and prose table carrying "skill"/"chain". This
                one anchors on the header ROW. Measured on this tree: the row form occurs once,
                the prose form sixteen times. Against the pre-P1 content at `2c1dbcc` it flags
                all ten cells including `doc-coauthoring` — it reddens on real history, not only
                on fixtures.

This docstring and the token comments below name `workflow.dev-lifecycle` and `team.quorum` as
literals — a detector cannot document or test what it may not name. That is a scoped exception for
this module's own definition site only; no other shipped surface may repeat either token literally.
"""
from __future__ import annotations

import re
from pathlib import Path

from enginelib.audit import Findings

# A dotted routing token: `workflow.dev-lifecycle`, `team.quorum`. Backticked or bare.
_DOTTED_RE = re.compile(r"\b((?:workflow|team)\.[a-z][a-z0-9-]*)")

# A reference to the retired origin-instance DATA root, in backticks or in a shell fragment. The
# lookbehind drops `/` from the exclusion class so a path-embedded `.ai` (e.g. `/path/to/.ai`) is
# visible; the path segment is optional so a bare `.ai` with no trailing slash still matches; the
# trailing negative lookahead keeps it from firing inside a longer token (`.aiff`, `.airc`,
# `example.ai`, `openai`).
_AI_ROOT_RE = re.compile(r"(?<![\w.-])(\.ai(?:/[A-Za-z0-9_./-]*)?)(?![\w-])")

# Lifecycle skill ids, prefix-agnostic — mirrors phantom_skills.py:33-36.
_LIFECYCLE = frozenset({
    "start", "processing", "done", "handoff",
    "forge", "hire", "retro", "feedback", "feedback-triage",
})


def find_dotted(text: str) -> list[tuple[int, str]]:
    """Every `workflow.*` / `team.*` token, as (1-indexed line number, token)."""
    out: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        for m in _DOTTED_RE.finditer(line):
            out.append((n, m.group(1)))
    return out


def find_ai_root_refs(text: str) -> list[tuple[int, str]]:
    """Every reference to the retired `.ai/` DATA root, as (1-indexed line number, path)."""
    out: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        for m in _AI_ROOT_RE.finditer(line):
            out.append((n, m.group(1)))
    return out


# The routing table's header ROW — deliberately not its vocabulary. `| Task Type | Skill Chain |`
# is an invocation table; a sentence containing the words "skill chain" is description. Measured
# on this tree: the row form occurs once, the prose form sixteen times. Anchoring on the row is
# the whole difference between this check and the prototype that measured 77% noise by matching
# any table header carrying "skill" / "workflow" / "chain".
_ROUTING_HEADER_RE = re.compile(r"^\|\s*Task Type\s*\|\s*Skill Chain\s*\|\s*$")

# One element of a chain: a kebab skill token, optionally `<plugin>:`-prefixed. Anything else in
# the cell is prose and is not a routing target.
_SKILL_TOKEN_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?::[a-z0-9]+(?:-[a-z0-9]+)*)?$")


def find_routing_cells(text: str) -> list[tuple[int, str, str]]:
    """Every skill token inside a routing table, as (1-indexed line, token, kind).

    `kind` is `prefixed` (carries a plugin prefix, so a missing one is visible as a missing
    plugin), `exempt` (bare but marked `†` — user-level, shipped by no plugin and unverifiable
    from the distribution) or `bare` (neither, which is how `doc-coauthoring` survived in
    start.md until it was found by hand).
    """
    out: list[tuple[int, str, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not _ROUTING_HEADER_RE.match(lines[i]):
            i += 1
            continue
        i += 2                                    # past the header and its |---|---| separator
        while i < len(lines) and lines[i].startswith("|"):
            chain = [c.strip() for c in lines[i].strip().strip("|").split("|")][-1]
            for element in chain.split("→"):
                token = element.strip()
                exempt = token.endswith("†")
                token = token.removesuffix("†").strip().strip("`")
                if not _SKILL_TOKEN_RE.match(token):
                    continue                      # prose, not a routing target
                kind = "exempt" if exempt else ("prefixed" if ":" in token else "bare")
                out.append((i + 1, token, kind))
            i += 1
    return out


def _resolves(token: str, skills_roots: list[Path], known_advisors: frozenset[str]) -> bool:
    """A dotted token resolves if something it could name actually exists.

    `team.<x>`: the lifecycle set or the discovered roster — those skills ship under `conclave:<x>`,
    so the `team.` spelling is a rename debt (loop-map.md §5), not a missing referent.
    `workflow.<x>`: a directory under some skills root. None is authored, by decision (spec 108 D2),
    so in practice this is always False — expressed as a lookup rather than a constant so an
    instance that does author one is not flagged for it.
    """
    if token.startswith("team."):
        bare = token.split(".", 1)[1]
        return bare in _LIFECYCLE or bare in known_advisors
    return any((root / token).is_dir() for root in skills_roots)


def run(
    surfaces: list[Path],
    skills_roots: list[Path],
    known_advisors: frozenset[str],
) -> Findings:
    """Resolve every routing target named by `surfaces`. Unresolvable targets are CRIT.

    A file that cannot be read is skipped, never raised — the caller decides which files exist.
    """
    crit: list[str] = []
    for path in surfaces:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for n, tok in find_dotted(text):
            if not _resolves(tok, skills_roots, known_advisors):
                crit.append(f"{path.name}:{n}: routing target does not exist: {tok}")
        for n, ref in find_ai_root_refs(text):
            crit.append(
                f"{path.name}:{n}: names the retired .ai/ DATA root (moved to .conclave/ "
                f"by spec 103): {ref}"
            )
        for n, tok, kind in find_routing_cells(text):
            if kind == "bare":
                crit.append(
                    f"{path.name}:{n}: routing cell carries neither a plugin prefix nor a "
                    f"† marker, so nothing can tell a real target from a phantom: {tok}"
                )
    return Findings(crit=crit, warn=[])
