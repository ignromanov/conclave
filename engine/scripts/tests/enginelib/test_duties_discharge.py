"""test_duties_discharge.py — the /conclave:done discharge check (spec 091 §4).

The check answers one question at session end: of the obligations in force for this agent,
which were addressed this session and which were not. It reports; it does not decide. A
deferred obligation is a normal outcome that must be visible, not an error to suppress.

The distinction these tests protect: only OBLIGATIONS are checked. Permissions and advice
are not owed, and a check that demanded them would make every session look delinquent —
which is how a governance signal gets ignored.

Hermetic: tmp_path only.
"""
from __future__ import annotations

from enginelib.duties.discharge import check_discharge
from enginelib.duties.ledger import append_entry
from enginelib.duties.model import Manifest, Mission, Norm, Role

CTO = Role(id="sage-cto", kind="advisor", inherits=["kind:advisor"])
CLOSE = Mission(id="m_session_close", goal="Close the session.")
GATE = Mission(id="m_quality_gate", goal="Run the gate.")
REVIEW = Mission(id="m_peer_review", goal="Ask for review.")


def _manifests(*norms):
    base = Manifest(version=1, missions=[CLOSE, GATE, REVIEW], norms=list(norms))
    return base, Manifest(version=1, roles=[CTO])


def test_obligation_with_a_ledger_entry_is_discharged(tmp_path):
    base, agent = _manifests(
        Norm(type="obligation", role="kind:advisor", mission="m_session_close"))
    append_entry(tmp_path, duty_id="m_session_close", session_id="s1", outcome="discharged")

    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.discharged == ["m_session_close"]
    assert r.deferred == []


def test_obligation_with_no_entry_is_deferred_not_discharged(tmp_path):
    base, agent = _manifests(
        Norm(type="obligation", role="kind:advisor", mission="m_session_close"))
    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.deferred == ["m_session_close"]
    assert r.discharged == []


def test_permissions_and_advice_are_never_owed(tmp_path):
    """A check that demanded permissions would mark every session delinquent, and a signal
    that always fires is a signal nobody reads."""
    base, agent = _manifests(
        Norm(type="permission", role="kind:advisor", mission="m_quality_gate"),
        Norm(type="advice", role="kind:advisor", mission="m_peer_review"),
    )
    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.deferred == [] and r.discharged == []


def test_only_this_session_counts(tmp_path):
    """An obligation discharged last session is owed again this one. Carrying credit forward
    would let one discharge satisfy an obligation forever."""
    base, agent = _manifests(
        Norm(type="obligation", role="kind:advisor", mission="m_session_close"))
    append_entry(tmp_path, duty_id="m_session_close", session_id="s0", outcome="discharged")

    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.deferred == ["m_session_close"]


def test_errored_and_skipped_are_not_discharged(tmp_path):
    """Attempting is not discharging. Counting an error as satisfaction is how a duty model
    starts reporting compliance it does not have."""
    base, agent = _manifests(
        Norm(type="obligation", role="kind:advisor", mission="m_session_close"))
    append_entry(tmp_path, duty_id="m_session_close", session_id="s1", outcome="errored")

    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.deferred == ["m_session_close"]
    assert r.discharged == []


def test_condition_unmet_is_neither_discharged_nor_deferred(tmp_path):
    """The condition did not hold, so nothing was owed. Reporting it as deferred would
    manufacture a debt out of a norm that never activated."""
    base, agent = _manifests(
        Norm(type="obligation", role="kind:advisor", mission="m_session_close",
             condition="phase:implementation"))
    append_entry(tmp_path, duty_id="m_session_close", session_id="s1",
                 outcome="condition-unmet")

    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.discharged == [] and r.deferred == []
    assert r.condition_unmet == ["m_session_close"]


def test_conditional_obligation_with_no_entry_is_reported_as_unevaluated(tmp_path):
    """`condition` is prose the LLM evaluates in context — this check cannot decide it. An
    unevaluated conditional must not be silently counted either way; it is surfaced so the
    agent answers it, which is the point at which the LLM is the right evaluator."""
    base, agent = _manifests(
        Norm(type="obligation", role="kind:advisor", mission="m_session_close",
             condition="phase:implementation"))
    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.unevaluated == ["m_session_close"]
    assert r.deferred == []


def test_unconditional_obligation_is_never_unevaluated(tmp_path):
    base, agent = _manifests(
        Norm(type="obligation", role="kind:advisor", mission="m_session_close"))
    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.unevaluated == []


def test_executor_obligations_do_not_reach_an_advisor(tmp_path):
    base, agent = _manifests(
        Norm(type="obligation", role="kind:executor", mission="m_quality_gate"))
    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.deferred == [] and r.discharged == []


def test_result_is_clean_only_when_nothing_is_owed(tmp_path):
    base, agent = _manifests(
        Norm(type="obligation", role="kind:advisor", mission="m_session_close"))
    assert not check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1").is_clean

    append_entry(tmp_path, duty_id="m_session_close", session_id="s1", outcome="discharged")
    assert check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1").is_clean


def test_an_agent_with_no_obligations_is_clean(tmp_path):
    base, agent = _manifests()
    assert check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1").is_clean


def test_an_unevaluated_conditional_obligation_is_not_clean(tmp_path):
    """`unevaluated` counts as owed. The agent still has to answer whether the condition
    held; treating it as clean would let every conditional obligation pass unexamined by
    the simple expedient of never mentioning it.

    Found by mutation: is_clean originally read `not self.deferred` alone and no test
    could tell the difference."""
    base, agent = _manifests(
        Norm(type="obligation", role="kind:advisor", mission="m_session_close",
             condition="phase:implementation"))
    r = check_discharge(base, agent, "sage-cto", tmp_path, session_id="s1")
    assert r.unevaluated == ["m_session_close"]
    assert not r.is_clean
