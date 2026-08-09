"""enginelib/skill_bind.py — write a verified skill into an agent-def's `skills:` list.

Spec 112 §2.1 intended this as the carrier that makes a bound skill real: the harness was to
preload the listed skills' **full content** into the subagent at startup, putting the skill in
context before the agent decides anything — the point being that an available-but-uninvoked
skill measured identically to no skill at all.

**§6b measured that carrier inert.** An agent whose def carried the key ~16 h before session
start reported the skill's body ABSENT, tools none, with an unbound control also ABSENT. The
harness's own agent frontmatter reference lists five fields and `skills` is not one of them.
Falsified for project-level defs; the plugin-shipped arm is untested. This module is therefore
correct about the *file* it produces and says nothing, any more, about what the harness loads.

I/O-free core: a pure text transform. The adapter resolves which repository the def lives in
(executor defs are CODE, advisor defs are project-side) and does the write.
"""
from __future__ import annotations

import re

_SKILLS = re.compile(r"^skills:\s*(.*)$")
_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):")


class BlockSequenceUnsupported(Exception):
    """`skills:` is written as a YAML block sequence, which this transform will not rewrite.

    Flattening it would silently discard whatever an author put there. One written form, and
    anything else is refused rather than reinterpreted.
    """


def _frontmatter_bounds(lines: list[str]) -> tuple[int, int]:
    if not lines or lines[0].strip() != "---":
        raise ValueError("file does not open with a frontmatter fence")
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return 1, i
    raise ValueError("unterminated frontmatter block")


def _parse_flow_list(value: str) -> list[str]:
    inner = value.strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        raise BlockSequenceUnsupported(f"skills: value is not a flow list: {value!r}")
    body = inner[1:-1].strip()
    return [item.strip() for item in body.split(",") if item.strip()] if body else []


def bind_skill(text: str, skill: str) -> tuple[str, bool]:
    """Return (new_text, changed) with `skill` present in the def's `skills:` list.

    Idempotent: re-binding an already-listed skill returns the input unchanged, so a caller
    that cannot remember what it did last time still cannot corrupt the roster.
    """
    if not skill or not skill.strip():
        raise ValueError("empty skill id")
    skill = skill.strip()

    lines = text.splitlines(keepends=True)
    start, end = _frontmatter_bounds([ln.rstrip("\n") for ln in lines])

    for i in range(start, end):
        m = _SKILLS.match(lines[i].rstrip("\n"))
        if not m:
            continue
        current = _parse_flow_list(m.group(1))
        if skill in current:
            return text, False
        current.append(skill)
        lines[i] = f"skills: [{', '.join(current)}]\n"
        return "".join(lines), True

    # Absent: insert after `tools:` when present — the canonical position pinned by
    # test_executor_frontmatter_is_canonical — else at the end of the frontmatter, which is
    # the only position that is correct for defs that carry a different field set.
    insert_at = end
    for i in range(start, end):
        key = _TOP_LEVEL_KEY.match(lines[i].rstrip("\n"))
        if key and key.group(1) == "tools":
            insert_at = i + 1
            break
    lines.insert(insert_at, f"skills: [{skill}]\n")
    return "".join(lines), True
