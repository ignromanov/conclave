"""test_roster_duty.py — duty files, the KAD scaffold, and description↔body drift
(spec 091 §3, acceptance 3).

A duty's `description` is what gets injected at startup; the body lazy-loads on trigger.
So the description is the only part that is always paid for, and a description that does
not describe its body is a duty the agent will never correctly trigger.

Hermetic: tmp_path only, except the one test that reads the shipped template.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from enginelib.duties.duty import DUTY_DESCRIPTION_MAX, load_duty

# The shipped-asset tests below assert about THIS checkout, so they anchor source-relative
# rather than calling duty.template_path(). Production code resolves through
# CONCLAVE_ENGINE_ROOT by design — and conftest deliberately leaves that var set — which in
# a git worktree points at the main checkout, i.e. a different tree than the one under test.
# Same split conftest already makes with _REAL_ENGINE_ROOT.
_CODE_ROOT = Path(__file__).resolve().parents[4]  # tests/enginelib -> tests -> scripts -> engine -> root


def template_path() -> Path:
    return _CODE_ROOT / "skills" / "forge-operations" / "roster" / "templates" / "DUTY.md"

VALID = """---
id: d_close_session
description: >-
  Files session artifacts before exit. Use when the session ends, /conclave:done runs,
  or handoff is mentioned.
goal: Leave no session unrecorded.
context:
  triggers: [session-end, conclave:done, handoff]
---

At session end, file the decision and session records through the engine CLI before
committing. A session that ends without a record cannot be resumed or audited.
"""


def _write(tmp_path, text, name="d_close_session.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_valid_duty_loads_with_id_description_and_body(tmp_path):
    d = load_duty(_write(tmp_path, VALID))
    assert d.id == "d_close_session"
    assert "Files session artifacts" in d.description
    assert "file the decision and session records" in d.body
    assert d.triggers == ["session-end", "conclave:done", "handoff"]


def test_empty_description_rejected(tmp_path):
    text = VALID.replace(
        "description: >-\n  Files session artifacts before exit. Use when the session ends, "
        "/conclave:done runs,\n  or handoff is mentioned.",
        'description: ""',
    )
    d = load_duty(_write(tmp_path, text))
    assert "empty-description" in [f.code for f in d.findings]


def test_missing_description_rejected(tmp_path):
    text = "\n".join(
        line for line in VALID.splitlines()
        if not line.startswith("description:") and not line.startswith("  Files")
        and not line.startswith("  or handoff")
    )
    d = load_duty(_write(tmp_path, text))
    assert "empty-description" in [f.code for f in d.findings]


def test_missing_id_rejected(tmp_path):
    text = VALID.replace("id: d_close_session\n", "")
    d = load_duty(_write(tmp_path, text))
    assert "missing-id" in [f.code for f in d.findings]


def test_overlong_description_rejected(tmp_path):
    text = VALID.replace("description: >-", "description: " + "x" * (DUTY_DESCRIPTION_MAX + 1) + "\nunused: >-")
    d = load_duty(_write(tmp_path, text))
    assert "description-too-long" in [f.code for f in d.findings]


def test_zero_overlap_between_description_and_body_is_drift(tmp_path):
    """The failure this catches: a duty edited in the body while its description kept
    describing the old behaviour. Nothing else in the system would notice."""
    text = VALID.replace(
        "At session end, file the decision and session records through the engine CLI before\n"
        "committing. A session that ends without a record cannot be resumed or audited.",
        "Rotate the TLS certificates on every deployment target and verify chain validity.",
    )
    d = load_duty(_write(tmp_path, text))
    assert "drifted" in [f.code for f in d.findings]


def test_matching_description_and_body_is_not_drift(tmp_path):
    d = load_duty(_write(tmp_path, VALID))
    assert "drifted" not in [f.code for f in d.findings]


def test_drift_ignores_stopwords(tmp_path):
    """Overlap on 'the'/'and'/'a' is not evidence of anything. If stopwords counted, drift
    detection would report clean on every pair of English sentences."""
    text = VALID.replace(
        "At session end, file the decision and session records through the engine CLI before\n"
        "committing. A session that ends without a record cannot be resumed or audited.",
        "The and a of the with and the a to the for and the in the on the at the by.",
    )
    d = load_duty(_write(tmp_path, text))
    assert "drifted" in [f.code for f in d.findings]


def test_clean_duty_has_no_findings(tmp_path):
    assert load_duty(_write(tmp_path, VALID)).findings == []


# --- P2: a duty declares what it covers, never how much force it carries --------------

def test_mission_defaults_to_the_duty_id(tmp_path):
    """`discharge.py:62` already keys the ledger by duty id and looks it up as
    `norm.mission`. The default makes that assumption explicit instead of implicit."""
    d = load_duty(_write(tmp_path, VALID))
    assert d.mission == "d_close_session"


def test_explicit_mission_is_kept(tmp_path):
    text = VALID.replace("goal: Leave no session unrecorded.",
                         "goal: Leave no session unrecorded.\nmission: m_session_close")
    d = load_duty(_write(tmp_path, text))
    assert d.mission == "m_session_close"


@pytest.mark.parametrize("declared", ["obligation", "advice", "permission"])
def test_a_duty_may_not_declare_its_own_force(tmp_path, declared):
    """§0 in executable form. **Do not delete this test quietly.**

    If a duty could set its own `type`, the agent the discharge check exists to catch would
    hold the key to its own lock — an edit softening `obligation` to `advice` would surface
    nowhere. Force is elevated only by the operator-owned norms file, so the finding must
    name that file rather than merely refusing the field.
    """
    text = VALID.replace("goal: Leave no session unrecorded.",
                         f"goal: Leave no session unrecorded.\ntype: {declared}")
    d = load_duty(_write(tmp_path, text))
    codes = [f.code for f in d.findings]
    assert "duty-declares-force" in codes, codes
    finding = next(f for f in d.findings if f.code == "duty-declares-force")
    assert "roster/norms.yaml" in finding.message, finding.message


def test_condition_is_carried_through_as_prose(tmp_path):
    text = VALID.replace("goal: Leave no session unrecorded.",
                         "goal: Leave no session unrecorded.\ncondition: the session mutated files")
    d = load_duty(_write(tmp_path, text))
    assert d.condition == "the session mutated files"
    assert d.findings == [], [f.code for f in d.findings]


def test_blank_condition_is_rejected(tmp_path):
    """Mirrors `Norm._condition_not_blank`: absent means unconditional, blank means someone
    meant to write one and did not. One rule, asserted in both homes."""
    text = VALID.replace("goal: Leave no session unrecorded.",
                         'goal: Leave no session unrecorded.\ncondition: "   "')
    d = load_duty(_write(tmp_path, text))
    assert "blank-condition" in [f.code for f in d.findings], [f.code for f in d.findings]


# --- the shipped scaffold must satisfy its own validator ------------------------------

def test_shipped_template_passes_its_own_validator():
    """A scaffold that fails the check it scaffolds for is a defect this project has
    shipped before. The template is the first thing every self-writing agent copies."""
    d = load_duty(template_path())
    assert d.findings == [], [f.code for f in d.findings]


def test_template_description_is_within_token_target():
    """Spec §3 targets 30-80 tokens. Asserted loosely in words — the point is that the
    scaffold cannot demonstrate the over-injection it exists to prevent."""
    d = load_duty(template_path())
    assert 8 <= len(d.description.split()) <= 90


@pytest.mark.parametrize("field", ["id", "description", "goal"])
def test_template_carries_every_required_field(field):
    d = load_duty(template_path())
    assert getattr(d, field)
