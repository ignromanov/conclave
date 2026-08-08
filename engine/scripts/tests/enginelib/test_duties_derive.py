"""test_duties_derive.py — a duty becomes a norm the registry can see (spec 091 P2 §0).

The seam this closes: `discharge.check_discharge` iterates norms, so a duty that is not a
norm can never be owed, and a skipped duty reported clean. Derivation puts every duty into
the norm namespace as **advice** — visible, and not yet binding.

Force is the operator's to grant: an operator norm at the default priority outranks derived
advice at 900 and elevates it to an obligation. That asymmetry is the whole design, so it is
asserted on the composed result rather than on the source files.
"""
from __future__ import annotations

import textwrap

import pytest

from enginelib.duties.derive import DERIVED_PRIORITY, derive
from enginelib.duties.duty import load_duty
from enginelib.duties.model import Manifest
from enginelib.duties.validate import compose, validate

DUTY = """---
id: d_diff_preview_before_edit
description: >-
  Shows the diff before applying it. Use when an edit is about to be written, or a file is
  about to be rewritten.
goal: Never write a change the operator has not seen.
---

Preview the diff before every Edit. A change applied unseen cannot be refused.
"""


def _duty(tmp_path, text=DUTY, name="d_diff_preview_before_edit.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return load_duty(p)


def _operator_norm(priority: int, ntype: str = "obligation") -> Manifest:
    """What the operator writes: ONE norm line, no roles: and no missions: block.
    Deriving those from the duty is what keeps elevation to a single line — §0.4."""
    import yaml
    data = yaml.safe_load(textwrap.dedent(f"""
        version: 1
        norms:
          - {{type: {ntype}, role: forge-chro, mission: d_diff_preview_before_edit,
              priority: {priority}}}
    """).strip())
    return Manifest(**data)


def test_a_duty_yields_one_advice_norm(tmp_path):
    m = derive([_duty(tmp_path)], "forge-chro", "advisor")
    assert len(m.norms) == 1
    norm = m.norms[0]
    assert (norm.type, norm.role, norm.mission) == (
        "advice", "forge-chro", "d_diff_preview_before_edit")


def test_derivation_declares_the_role_and_the_mission_it_references(tmp_path):
    """Emitting the norm alone would make the composed registry report `unknown-mission`
    AND `unknown-role` — both measured firing on the live tree (plan §0.4). The operator
    would then have to hand-write three blocks to make one duty binding, and the cost of
    elevation is what decides whether this mechanism is ever used."""
    m = derive([_duty(tmp_path)], "forge-chro", "advisor")
    assert [r.id for r in m.roles] == ["forge-chro"]
    assert [ms.id for ms in m.missions] == ["d_diff_preview_before_edit"]

    findings = validate([m])
    assert findings == [], [f.code for f in findings]


def test_the_derived_mission_carries_the_duty_goal(tmp_path):
    m = derive([_duty(tmp_path)], "forge-chro", "advisor")
    assert m.missions[0].goal == "Never write a change the operator has not seen."


def test_an_operator_norm_elevates_derived_advice_to_an_obligation(tmp_path):
    """Assert the COMPOSED result, not the source files — what the discharge check sees is
    the only thing that matters here."""
    derived = derive([_duty(tmp_path)], "forge-chro", "advisor")
    composed = compose([derived, _operator_norm(priority=100)])

    effective = composed.for_role("forge-chro")
    assert len(effective) == 1
    assert effective[0].type == "obligation", (
        f"operator norm at 100 must outrank derived advice at {DERIVED_PRIORITY}")


def test_an_operator_norm_at_the_same_priority_is_a_conflict_not_a_coin_toss(tmp_path):
    """The existing precedence rule must keep biting through derivation: equal priority with
    different deontic types has no defined winner, and silently picking one would make the
    registry's answer depend on load order."""
    derived = derive([_duty(tmp_path)], "forge-chro", "advisor")
    findings = validate([derived, _operator_norm(priority=DERIVED_PRIORITY)])
    assert "priority-conflict" in [f.code for f in findings], [f.code for f in findings]


def test_derived_advice_loses_to_the_default_priority(tmp_path):
    """The constant's whole job: an operator writing a norm without thinking about numbers
    still wins. If DERIVED_PRIORITY ever drops below the Norm default, this goes red."""
    from enginelib.duties.model import Norm

    assert DERIVED_PRIORITY > Norm.model_fields["priority"].default


@pytest.mark.parametrize("kind", ["advisor", "executor"])
def test_the_derived_role_inherits_its_abstract_tier(tmp_path, kind):
    """Base norms reach concrete roles through `kind:*`. A derived role that inherits
    nothing would be invisible to every norm the engine ships."""
    m = derive([_duty(tmp_path)], "some-agent", kind)
    assert m.roles[0].kind == kind
    assert f"kind:{kind}" in m.roles[0].inherits


def test_no_duties_derives_an_empty_manifest_not_a_dangling_role(tmp_path):
    m = derive([], "forge-chro", "advisor")
    assert m.norms == [] and m.missions == [] and m.roles == []
