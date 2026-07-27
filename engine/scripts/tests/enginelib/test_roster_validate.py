"""test_roster_validate.py — norm validator rules (spec 091 §1 acceptance 1).

One test per rule, each written so that deleting its rule from validate.py turns exactly
this test red and nothing else. A validator rule with no test that can fail is decoration.

Hermetic: model objects only, no disk.
"""
from __future__ import annotations

from enginelib.roster.model import Manifest, Mission, Norm, Role
from enginelib.roster.validate import compose, validate


def _m(roles=(), missions=(), norms=()):
    return Manifest(version=1, roles=list(roles), missions=list(missions), norms=list(norms))


def _codes(findings):
    return sorted(f.code for f in findings)


ADVISOR = Role(id="cto", kind="advisor", inherits=["kind:advisor"])
CLOSE = Mission(id="m_session_close", goal="Close the session with artifacts filed.")


def test_clean_manifest_yields_no_findings():
    m = _m([ADVISOR], [CLOSE], [Norm(type="obligation", role="cto", mission="m_session_close")])
    assert validate([m]) == []


# --- referential integrity ------------------------------------------------------------

def test_norm_referencing_unknown_mission_is_reported_by_name():
    m = _m([ADVISOR], [CLOSE], [Norm(type="advice", role="cto", mission="m_ghost")])
    findings = validate([m])
    assert _codes(findings) == ["unknown-mission"]
    assert "m_ghost" in findings[0].message


def test_norm_referencing_unknown_role_is_reported_by_name():
    m = _m([ADVISOR], [CLOSE], [Norm(type="advice", role="wizard", mission="m_session_close")])
    findings = validate([m])
    assert _codes(findings) == ["unknown-role"]
    assert "wizard" in findings[0].message


def test_abstract_roles_are_always_known():
    """`all` / `kind:advisor` / `kind:executor` need no declaration — they are the
    engine's fixed abstract tier, and base norms attach to nothing else."""
    m = _m([ADVISOR], [CLOSE],
           [Norm(type="obligation", role="kind:advisor", mission="m_session_close")])
    assert validate([m]) == []


def test_role_inheriting_an_undeclared_parent_is_reported():
    orphan = Role(id="cfo", kind="advisor", inherits=["kind:accountant"])
    m = _m([orphan], [CLOSE], [])
    findings = validate([m])
    assert _codes(findings) == ["unknown-parent-role"]
    assert "kind:accountant" in findings[0].message


# --- priority conflict ----------------------------------------------------------------

def test_same_role_mission_at_equal_priority_is_a_conflict():
    """Spec §2: same-priority conflict is a validation error, not a silent pick. Two norms
    that disagree at equal precedence have no defined winner — refusing is the only
    answer that cannot be wrong."""
    m = _m([ADVISOR], [CLOSE], [
        Norm(type="obligation", role="cto", mission="m_session_close", priority=50),
        Norm(type="permission", role="cto", mission="m_session_close", priority=50),
    ])
    assert _codes(validate([m])) == ["priority-conflict"]


def test_identical_type_at_equal_priority_is_not_a_conflict():
    """Same verdict twice is redundant, not contradictory — base and agent may both
    assert the same obligation."""
    m = _m([ADVISOR], [CLOSE], [
        Norm(type="obligation", role="cto", mission="m_session_close", priority=50),
        Norm(type="obligation", role="cto", mission="m_session_close", priority=50),
    ])
    assert validate([m]) == []


def test_different_priorities_resolve_without_conflict():
    m = _m([ADVISOR], [CLOSE], [
        Norm(type="obligation", role="cto", mission="m_session_close", priority=50),
        Norm(type="permission", role="cto", mission="m_session_close", priority=100),
    ])
    assert validate([m]) == []


# --- composition + inheritance --------------------------------------------------------

def test_norm_on_abstract_role_is_inherited_by_concrete_holder():
    """Assert the COMPOSED set, not the source file — inheritance is the mechanism that
    lets the engine base reach a concrete agent without duplicating a line into it."""
    base = _m([], [CLOSE],
              [Norm(type="obligation", role="kind:advisor", mission="m_session_close")])
    agent = _m([ADVISOR], [], [])
    composed = compose([base, agent])
    assert [n.mission for n in composed.for_role("cto")] == ["m_session_close"]


def test_all_role_reaches_advisors_and_executors_alike():
    base = _m([], [CLOSE], [Norm(type="advice", role="all", mission="m_session_close")])
    agent = _m([ADVISOR, Role(id="iris-test", kind="executor", inherits=["kind:executor"])],
               [], [])
    composed = compose([base, agent])
    assert composed.for_role("cto") and composed.for_role("iris-test")


def test_executor_does_not_inherit_advisor_norms():
    """The abstract tier is a partition, not a chain. An executor picking up advisor
    obligations is how a duty model starts asserting things no one agreed to."""
    base = _m([], [CLOSE],
              [Norm(type="obligation", role="kind:advisor", mission="m_session_close")])
    agent = _m([Role(id="iris-test", kind="executor", inherits=["kind:executor"])], [], [])
    assert compose([base, agent]).for_role("iris-test") == []


def test_lower_priority_number_wins():
    """Nix convention, spec §2: lower number = higher precedence. This is the single most
    invertible detail in the spec, so the direction is asserted rather than implied."""
    base = _m([], [CLOSE],
              [Norm(type="advice", role="kind:advisor", mission="m_session_close", priority=100)])
    agent = _m([ADVISOR], [],
               [Norm(type="obligation", role="cto", mission="m_session_close", priority=10)])
    effective = compose([base, agent]).for_role("cto")
    assert [n.type for n in effective] == ["obligation"]


def test_agent_norm_overrides_base_only_by_priority_not_by_being_later():
    """Source order must not decide precedence — otherwise file layout silently becomes
    policy and the `priority` field means nothing."""
    base = _m([], [CLOSE],
              [Norm(type="obligation", role="kind:advisor", mission="m_session_close", priority=10)])
    agent = _m([ADVISOR], [],
               [Norm(type="advice", role="cto", mission="m_session_close", priority=100)])
    effective = compose([base, agent]).for_role("cto")
    assert [n.type for n in effective] == ["obligation"]


def test_findings_carry_a_stable_code_and_a_message():
    m = _m([ADVISOR], [], [Norm(type="advice", role="cto", mission="m_ghost")])
    f = validate([m])[0]
    assert f.code and f.message and f.severity in ("error", "warning")
