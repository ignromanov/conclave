"""test_roster_schema.py — the deontic tuple (spec 091 §2).

A norm is {type, role, mission, condition, priority}. These tests pin the shape and, more
importantly, pin what is REJECTED — a schema that accepts everything validates nothing.

Hermetic: pure model construction, no disk.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from enginelib.roster.model import Manifest, Mission, Norm, Role


def _norm(**over):
    base = {"type": "obligation", "role": "kind:advisor", "mission": "m_session_close",
            "condition": "phase:done", "priority": 100}
    return {**base, **over}


def test_valid_norm_parses():
    n = Norm(**_norm())
    assert n.type == "obligation"
    assert n.role == "kind:advisor"
    assert n.priority == 100


@pytest.mark.parametrize("type_", ["obligation", "permission", "advice"])
def test_all_three_deontic_types_accepted(type_):
    """The vocabulary is exactly three. Capabilities are `permission` norms over
    capability-missions (spec §2) — not a fourth type."""
    assert Norm(**_norm(type=type_)).type == type_


def test_unknown_deontic_type_rejected():
    with pytest.raises(ValidationError) as e:
        Norm(**_norm(type="requirement"))
    assert "type" in str(e.value)


def test_missing_role_rejected():
    payload = _norm()
    del payload["role"]
    with pytest.raises(ValidationError) as e:
        Norm(**payload)
    assert "role" in str(e.value)


def test_missing_mission_rejected():
    payload = _norm()
    del payload["mission"]
    with pytest.raises(ValidationError) as e:
        Norm(**payload)
    assert "mission" in str(e.value)


def test_non_integer_priority_rejected():
    with pytest.raises(ValidationError):
        Norm(**_norm(priority="high"))


def test_empty_condition_rejected():
    """`condition` is prose the LLM evaluates in context (research §E rejects a rule
    engine). Empty prose is not a condition — an always-true norm must say so."""
    with pytest.raises(ValidationError) as e:
        Norm(**_norm(condition="   "))
    assert "condition" in str(e.value)


def test_absent_condition_is_unconditional():
    """Omitting `condition` entirely is legal and means 'always active' — distinct from
    supplying an empty string, which is a typo."""
    payload = _norm()
    del payload["condition"]
    assert Norm(**payload).condition is None


def test_condition_is_not_parsed_or_executed():
    """Guard against the rejected design re-entering: arbitrary prose passes through
    verbatim. If this test ever needs a grammar, spec 091's §E decision was reversed."""
    prose = "when the operator has approved the contract AND rigor != lite"
    assert Norm(**_norm(condition=prose)).condition == prose


def test_mission_requires_id_and_goal():
    m = Mission(id="m_session_close", goal="Close the session with artifacts filed.")
    assert m.id == "m_session_close"
    with pytest.raises(ValidationError):
        Mission(id="m_x")


def test_role_inherits_declared_parents():
    r = Role(id="cto", kind="advisor", inherits=["kind:advisor"])
    assert r.inherits == ["kind:advisor"]


def test_role_kind_is_advisor_or_executor():
    with pytest.raises(ValidationError):
        Role(id="ghost", kind="daemon")


def test_manifest_collects_roles_missions_norms():
    m = Manifest(
        version=1,
        roles=[Role(id="cto", kind="advisor", inherits=["kind:advisor"])],
        missions=[Mission(id="m_session_close", goal="Close the session.")],
        norms=[Norm(**_norm(role="cto"))],
    )
    assert [r.id for r in m.roles] == ["cto"]
    assert len(m.norms) == 1


def test_manifest_defaults_to_empty_collections():
    """A base file carrying only `version:` must parse — that is the shipped empty state."""
    m = Manifest(version=1)
    assert m.roles == [] and m.missions == [] and m.norms == []


# --- generated JSON-Schema stays in lockstep with the models -------------------------------

def test_committed_json_schemas_match_regeneration():
    """The JSON-Schemas under roster/schema/ are GENERATED from these models. Two
    hand-maintained copies of one fact is the P3 single-owner violation acceptance §8
    names; this test is what keeps it one fact."""
    from enginelib.roster.model import SCHEMA_FILES, schema_dir

    assert SCHEMA_FILES, "schema export list is empty — nothing would be checked"
    for name, model in SCHEMA_FILES.items():
        path = schema_dir() / f"{name}.schema.json"
        assert path.exists(), f"{path} missing — run `engine duty schema --write`"
        committed = json.loads(path.read_text())
        assert committed == model.model_json_schema(), (
            f"{name}.schema.json is stale — regenerate with `engine duty schema --write`"
        )
