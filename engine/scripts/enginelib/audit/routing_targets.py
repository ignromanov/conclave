"""enginelib/audit/routing_targets.py — resolve every routing target a shipped command names (108 P1).

I/O-free: no print / argparse / sys.exit. Reads only the files it is handed and returns
Findings(crit=[...], warn=[]).

Why this is separate from phantom_skills.py: that scanner covers the advisor-*authored* surface
and skips lifecycle skills by design (phantom_skills.py:127), and its token regex admits a dot
only in the `team.<name>` form. A routing target written `workflow.dev-lifecycle` inside
commands/start.md is therefore invisible to it twice over. The two modules cover disjoint surfaces.

Two checks, each exact — a third, heuristic one was prototyped at 77% noise and dropped rather
than shipped with an exclusion list (plan-p1.md D-6):

  1. dotted   — `workflow.x` never resolves (none is authored, by decision: spec 108 D2).
                `team.x` is a NAMING debt, not a phantom — those skills exist under `conclave:x` —
                so it resolves against the lifecycle set plus the discovered roster, the same rule
                phantom_skills.py:95-98 uses. Only `team.quorum` survives that, which is what
                loop-map.md §5 measured independently.
  2. ai-root  — no shipped surface may name a path under `.ai/`. That was the origin instance's
                DATA root; spec 103 moved DATA to `.conclave/` and `.ai/` exists nowhere in this
                repo. Twelve live command instructions still operated on it when this check was
                written, two of them in steps that run every session.

NOT covered, deliberately: bare-kebab routing cells such as `doc-coauthoring`. See D-6.
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
    return Findings(crit=crit, warn=[])
