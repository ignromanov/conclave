"""tests/test_feedback_schema_constraints.py — #52 documented schema constraints.

Locks the two field-type rules the emit scaffold + 086 field table now document,
after a First-Launch finalize rejected all 9 items on undocumented constraints:
  - item `id` must be a STRING (a bare YAML int is type-invalid)
  - `location.skill` must be a skill-path slug (team.*/exec.*/workflow.*/util.*),
    not a bare agent name.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from feedback.schema import FeedbackItem, Location

_BASE = dict(
    category="script-defect",
    layer="skill",
    observation="x",
    suggested_fix="y",
    severity="low",
    frequency="first-time",
    evidence="tool:1",
)


def test_int_id_is_rejected():
    with pytest.raises(ValidationError):
        FeedbackItem(id=1, location=Location(file="a.py"), **_BASE)


def test_string_id_is_accepted():
    item = FeedbackItem(id="i1", location=Location(file="a.py"), **_BASE)
    assert item.id == "i1"


@pytest.mark.parametrize("bad", ["sage-cto", "kai", "team", "randomname"])
def test_bare_agent_name_skill_rejected(bad):
    with pytest.raises(ValidationError):
        Location(skill=bad)


@pytest.mark.parametrize("good", ["team.sage-cto", "exec.iris-test", "workflow.foo", "util.fix"])
def test_skill_path_slug_accepted(good):
    assert Location(skill=good).skill == good
