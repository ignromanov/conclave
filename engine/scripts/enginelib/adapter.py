"""enginelib/adapter.py — per-advisor adapter files for external skills (spec 108 §3.1).

An external skill carries its own schema and we do not own its file. The adapter is our
wrapper: it lives in the advisor's own home, carries our frontmatter, and names the foreign
skill through `external_skill:`. `skills:` in an agent-def says *that* a skill is loaded; the
adapter says *why* — at which stage, for which task type, binding or advisory — which a bare
list cannot express.

The axis rules are 108 §5's and are deliberately strict: all three axes required, closed enums,
no wildcard, no "absent means all". Each was chosen against named precedent (VS Code discourages
its own `*`; ESLint's absent-`files` is a documented trap), so none of them is softened here.

I/O-free core: renders and validates text. The adapter writes the file.
"""
from __future__ import annotations

import re

STAGES: frozenset[str] = frozenset(
    {"clarify", "design", "spec", "plan", "implement", "verify", "deliver"}
)
TIERS: frozenset[str] = frozenset({"quick", "work"})
TASK_TYPES: frozenset[str] = frozenset({"dev", "content", "research", "review", "advisory"})
BINDINGS: frozenset[str] = frozenset({"required", "advisory"})

_AXES: dict[str, frozenset[str]] = {
    "stages": STAGES,
    "tiers": TIERS,
    "task_types": TASK_TYPES,
}
_LIST_LINE = re.compile(r"^(stages|tiers|task_types):\s*\[(.*)\]\s*$")
_SCALAR_LINE = re.compile(r"^(binding|last-reviewed|external_skill):\s*(\S.*)$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def render_adapter(
    *,
    skill: str,
    stages: list[str],
    tiers: list[str],
    task_types: list[str],
    binding: str,
    last_reviewed: str,
    rationale: str,
) -> str:
    """Build an adapter file. Raises ValueError on anything the validator would reject.

    Rendering validates rather than trusting the caller: a file that has to be written before
    its errors are visible is a file that gets written wrong once and read wrong forever.
    """
    problems = _check(
        {"stages": stages, "tiers": tiers, "task_types": task_types},
        binding,
        last_reviewed,
        skill,
    )
    if problems:
        raise ValueError("; ".join(problems))
    if not rationale.strip():
        raise ValueError("empty rationale — the adapter exists to carry the reason")

    return (
        "---\n"
        f"stages: [{', '.join(stages)}]\n"
        f"tiers: [{', '.join(tiers)}]\n"
        f"task_types: [{', '.join(task_types)}]\n"
        f"binding: {binding}\n"
        f"last-reviewed: {last_reviewed}\n"
        f"external_skill: {skill}\n"
        "---\n\n"
        f"{rationale.strip()}\n"
    )


def _check(
    axes: dict[str, list[str]], binding: str, last_reviewed: str, skill: str
) -> list[str]:
    problems: list[str] = []
    for name, allowed in _AXES.items():
        values = axes.get(name) or []
        if not values:
            problems.append(f"{name}: required and must be non-empty (no 'absent means all')")
            continue
        if "*" in values:
            problems.append(f"{name}: wildcard is not an axis value")
        unknown = sorted(set(values) - allowed)
        if unknown:
            problems.append(f"{name}: unknown {unknown} (allowed: {sorted(allowed)})")
    if binding not in BINDINGS:
        problems.append(f"binding: must be one of {sorted(BINDINGS)}, got {binding!r}")
    if not _ISO_DATE.match(last_reviewed or ""):
        problems.append(f"last-reviewed: must be YYYY-MM-DD, got {last_reviewed!r}")
    if not skill or not skill.strip():
        problems.append("external_skill: required")
    return problems


def validate_adapter(text: str) -> list[str]:
    """Return the problems in an adapter file; empty means valid."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ["no frontmatter fence"]
    try:
        end = lines.index("---", 1)
    except ValueError:
        return ["unterminated frontmatter"]

    axes: dict[str, list[str]] = {}
    scalars: dict[str, str] = {}
    for line in lines[1:end]:
        m = _LIST_LINE.match(line)
        if m:
            body = m.group(2).strip()
            axes[m.group(1)] = [v.strip() for v in body.split(",") if v.strip()]
            continue
        s = _SCALAR_LINE.match(line)
        if s:
            scalars[s.group(1)] = s.group(2).strip()

    problems = _check(
        axes,
        scalars.get("binding", ""),
        scalars.get("last-reviewed", ""),
        scalars.get("external_skill", ""),
    )
    if not "".join(lines[end + 1:]).strip():
        problems.append("empty body — the adapter exists to carry the reason")
    return problems
