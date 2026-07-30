"""test_duties_project.py — the COMPUTED-DUTIES.md projection (spec 091 §3, acceptance 2).

The projection is what every holder of a duty pays for at startup, on every session. Spec §3
names over-injection as the top failure mode, so most of these tests assert what the file
must NOT contain. Those are the load-bearing ones: a projection that grows bodies still
"works", it just quietly costs every session more context than it saves.

Hermetic: tmp_path only.
"""
from __future__ import annotations

from enginelib.duties.model import Manifest, Mission, Norm, Role
from enginelib.duties.project import project_agent, render_projection

CLOSE = Mission(id="m_session_close", goal="Close the session with artifacts filed.")
GATE = Mission(id="m_quality_gate", goal="Run the quality gate before delivery.")
CTO = Role(id="sage-cto", kind="advisor", inherits=["kind:advisor"])
IRIS = Role(id="iris-test", kind="executor", inherits=["kind:executor"])

DUTY_A = """---
id: d_close_session
description: Files session artifacts before exit. Use when the session ends or handoff is mentioned.
goal: Leave no session unrecorded.
---

At session end, file the decision and session records through the engine CLI. The body is
long deliberately, so a projection that leaked bodies would be obvious in the assertions
below rather than merely larger.
"""

DUTY_B = """---
id: d_quality_gate
description: Runs lint, types and tests before a verdict. Use when delivery or a gate is mentioned.
goal: No verdict without evidence.
---

Run the full gate and report counts, not impressions.
"""


def _duties(tmp_path, *texts):
    d = tmp_path / "duties"
    d.mkdir(exist_ok=True)
    for i, text in enumerate(texts):
        (d / f"duty{i}.md").write_text(text, encoding="utf-8")
    return d


def _base():
    return Manifest(
        version=1,
        missions=[CLOSE, GATE],
        norms=[
            Norm(type="obligation", role="kind:advisor", mission="m_session_close"),
            Norm(type="obligation", role="kind:executor", mission="m_quality_gate"),
        ],
    )


def test_projection_is_one_line_per_duty(tmp_path):
    duties = _duties(tmp_path, DUTY_A, DUTY_B)
    text = render_projection("sage-cto", project_agent(_base(), Manifest(version=1, roles=[CTO]),
                                                       "sage-cto", duties))
    body_lines = [ln for ln in text.splitlines() if ln.startswith("d_")]
    assert len(body_lines) == 2
    assert all(ln.count("\n") == 0 for ln in body_lines)


def test_projection_uses_duty_id_colon_description_shape(tmp_path):
    duties = _duties(tmp_path, DUTY_A)
    text = render_projection("sage-cto", project_agent(_base(), Manifest(version=1, roles=[CTO]),
                                                       "sage-cto", duties))
    assert "d_close_session: Files session artifacts before exit." in text


def test_projection_never_contains_duty_bodies(tmp_path):
    """The whole point of progressive disclosure. If this fails, every session of every
    holder pays for text that lazy-loading was supposed to defer."""
    duties = _duties(tmp_path, DUTY_A, DUTY_B)
    text = render_projection("sage-cto", project_agent(_base(), Manifest(version=1, roles=[CTO]),
                                                       "sage-cto", duties))
    assert "file the decision and session records" not in text
    assert "report counts, not impressions" not in text


def test_projection_is_not_yaml(tmp_path):
    """Spec §3: never YAML. A structured dump invites a consumer to parse and re-inject it."""
    duties = _duties(tmp_path, DUTY_A)
    text = render_projection("sage-cto", project_agent(_base(), Manifest(version=1, roles=[CTO]),
                                                       "sage-cto", duties))
    assert not text.lstrip().startswith("---")
    assert "  - " not in text and "duties:" not in text


def test_duty_order_is_deterministic(tmp_path):
    """Sorted by id, so the file does not churn between runs and a diff means a change."""
    duties = _duties(tmp_path, DUTY_B, DUTY_A)
    text = render_projection("sage-cto", project_agent(_base(), Manifest(version=1, roles=[CTO]),
                                                       "sage-cto", duties))
    ids = [ln.split(":")[0] for ln in text.splitlines() if ln.startswith("d_")]
    assert ids == sorted(ids)


def test_two_runs_are_byte_identical(tmp_path):
    duties = _duties(tmp_path, DUTY_A, DUTY_B)
    args = (_base(), Manifest(version=1, roles=[CTO]), "sage-cto", duties)
    assert render_projection("sage-cto", project_agent(*args)) == \
           render_projection("sage-cto", project_agent(*args))


def test_projection_lists_active_obligations_for_the_role(tmp_path):
    p = project_agent(_base(), Manifest(version=1, roles=[CTO]), "sage-cto", _duties(tmp_path))
    assert [n.mission for n in p.norms] == ["m_session_close"]


def test_executor_projection_gets_executor_norms_not_advisor_ones(tmp_path):
    """Executors are the tier 091 exists to give duties to at all. If the partition leaks
    here, an executor's first-ever projection asserts obligations meant for advisors."""
    p = project_agent(_base(), Manifest(version=1, roles=[IRIS]), "iris-test", _duties(tmp_path))
    assert [n.mission for n in p.norms] == ["m_quality_gate"]


def test_agent_with_no_duties_projects_an_explicit_empty_state(tmp_path):
    """A missing duties/ dir is a normal state, not an error — most agents will start there.
    The file still renders, so its absence never reads as 'projection not run'."""
    text = render_projection("sage-cto", project_agent(_base(), Manifest(version=1, roles=[CTO]),
                                                       "sage-cto", tmp_path / "nope"))
    assert "sage-cto" in text
    assert "none" in text.lower()


def test_projection_reports_duty_findings_without_dropping_the_duty(tmp_path):
    """A drifted or description-less duty still projects — refusing to render would hide
    every other duty the agent holds behind one bad file."""
    broken = DUTY_A.replace(
        "description: Files session artifacts before exit. Use when the session ends or "
        "handoff is mentioned.", 'description: ""')
    p = project_agent(_base(), Manifest(version=1, roles=[CTO]), "sage-cto",
                      _duties(tmp_path, broken))
    assert len(p.duties) == 1
    assert any(f.code == "empty-description" for f in p.findings)
