"""tests/enginelib/test_skill_bind.py — binding a skill into an agent-def (spec 112 T3).

`skills:` was meant to be what makes a bound skill real — the harness preloading the skill's
full content into the subagent at startup. Spec 112 §6b measured that ABSENT for a project-level
def, so what these tests pin is the file, not the load: a well-formed, idempotent, phantom-refusing
key. Editing frontmatter by hand is how rosters get corrupted, so the edit is a pure text transform
tested here and a thin file write in the adapter. No test below asserts the harness reads it —
that claim needs a dispatch, and a dispatch is not a unit test.
"""
from __future__ import annotations

import pytest

from enginelib.skill_bind import BlockSequenceUnsupported, bind_skill

_DEF = """---
name: exec-techne-skills
description: >-
  🧰 Finds the skills a task needs.
tools: Read, Write, Grep
model: sonnet
tier: executor
---

# body stays untouched

- `skills:` in prose must not be edited
"""


def _frontmatter(text: str) -> list[str]:
    lines = text.splitlines()
    end = lines.index("---", 1)
    return lines[1:end]


def test_creates_the_field_after_tools():
    out, changed = bind_skill(_DEF, "pytest-advanced")
    assert changed
    keys = [ln.split(":", 1)[0] for ln in _frontmatter(out) if not ln.startswith(" ")]
    assert keys.index("skills") == keys.index("tools") + 1
    assert keys.index("skills") < keys.index("model")
    assert "skills: [pytest-advanced]" in out


def test_appends_to_an_existing_list():
    once, _ = bind_skill(_DEF, "pytest-advanced")
    twice, changed = bind_skill(once, "bash-defensive-patterns")
    assert changed
    assert "skills: [pytest-advanced, bash-defensive-patterns]" in twice


def test_is_idempotent():
    """Binding the same skill twice yields one entry. The naive append gets this wrong."""
    once, _ = bind_skill(_DEF, "pytest-advanced")
    again, changed = bind_skill(once, "pytest-advanced")
    assert not changed
    assert again == once


def test_body_is_untouched():
    out, _ = bind_skill(_DEF, "pytest-advanced")
    assert out.split("---", 2)[2] == _DEF.split("---", 2)[2]


def test_refuses_a_block_sequence_rather_than_corrupting_it():
    """We write one form; anything else is refused, not rewritten.

    A def hand-edited into block style is still valid YAML, and silently flattening it would
    lose whatever the author put there. Refusing is the honest failure.
    """
    block = _DEF.replace("tools: Read, Write, Grep", "tools: Read\nskills:\n  - already-here")
    with pytest.raises(BlockSequenceUnsupported):
        bind_skill(block, "pytest-advanced")


def test_a_def_without_tools_still_binds():
    """Advisor defs do not all carry the executor field set."""
    minimal = "---\nname: sage-cto\ndescription: x\ncolor: cyan\n---\n\nbody\n"
    out, changed = bind_skill(minimal, "vitest")
    assert changed
    assert "skills: [vitest]" in out


def test_a_file_without_frontmatter_is_refused():
    with pytest.raises(ValueError):
        bind_skill("# just a heading\n", "vitest")
