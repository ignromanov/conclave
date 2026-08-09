"""tests/enginelib/test_adapter.py — the 108 §3.1 adapter schema (spec 112 T4).

Each rejection below is a planted defect: the axis rules were chosen against named precedent
(VS Code discourages its own `*`; ESLint's absent-`files` is a documented trap), so a validator
that accepted them would be softening a decision rather than implementing it.
"""
from __future__ import annotations

import pytest

from enginelib.adapter import render_adapter, validate_adapter

_GOOD = dict(
    skill="pytest-advanced",
    stages=["implement", "verify"],
    tiers=["work"],
    task_types=["dev"],
    binding="required",
    last_reviewed="2026-08-09",
    rationale="sage-cto reaches for this whenever an engine test needs a fixture rethought.",
)


def test_round_trip_is_valid():
    assert validate_adapter(render_adapter(**_GOOD)) == []


def test_rendered_shape_is_the_documented_one():
    out = render_adapter(**_GOOD)
    assert "stages: [implement, verify]" in out
    assert "external_skill: pytest-advanced" in out
    assert out.startswith("---\n")


@pytest.mark.parametrize("axis", ["stages", "tiers", "task_types"])
def test_an_empty_axis_is_rejected(axis):
    """No 'absent means all'. An axis left off must fail, not quietly widen."""
    with pytest.raises(ValueError, match=axis):
        render_adapter(**{**_GOOD, axis: []})


@pytest.mark.parametrize("axis", ["stages", "tiers", "task_types"])
def test_a_wildcard_is_not_an_axis_value(axis):
    with pytest.raises(ValueError, match="wildcard"):
        render_adapter(**{**_GOOD, axis: ["*"]})


def test_unknown_enum_member_is_rejected():
    with pytest.raises(ValueError, match="unknown"):
        render_adapter(**{**_GOOD, "stages": ["implement", "deploy"]})


def test_binding_is_a_closed_pair():
    with pytest.raises(ValueError, match="binding"):
        render_adapter(**{**_GOOD, "binding": "maybe"})


def test_last_reviewed_must_be_a_date():
    with pytest.raises(ValueError, match="last-reviewed"):
        render_adapter(**{**_GOOD, "last_reviewed": "yesterday"})


def test_an_empty_rationale_is_rejected():
    """The adapter's only advantage over a bare `skills:` entry is the reason it carries."""
    with pytest.raises(ValueError, match="rationale"):
        render_adapter(**{**_GOOD, "rationale": "   "})


def test_validator_catches_a_hand_edited_file():
    """Files get edited after they are written; the validator is not just a render check."""
    tampered = render_adapter(**_GOOD).replace("tiers: [work]", "tiers: [*]")
    assert any("wildcard" in p for p in validate_adapter(tampered))


def test_validator_rejects_a_missing_axis_line():
    stripped = "\n".join(
        ln for ln in render_adapter(**_GOOD).splitlines() if not ln.startswith("task_types:")
    )
    assert any("task_types" in p for p in validate_adapter(stripped))


def test_validator_rejects_an_empty_body():
    head = render_adapter(**_GOOD).split("---", 2)[:2]
    assert any("empty body" in p for p in validate_adapter("---".join(head) + "---\n\n"))


def test_validator_rejects_a_file_without_frontmatter():
    assert validate_adapter("just prose\n") == ["no frontmatter fence"]
