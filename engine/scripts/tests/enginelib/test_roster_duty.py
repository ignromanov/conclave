"""test_roster_duty.py — duty files, the KAD scaffold, and description↔body drift
(spec 091 §3, acceptance 3).

A duty's `description` is what gets injected at startup; the body lazy-loads on trigger.
So the description is the only part that is always paid for, and a description that does
not describe its body is a duty the agent will never correctly trigger.

Hermetic: tmp_path only, except the one test that reads the shipped template.
"""
from __future__ import annotations

import pytest

from enginelib.roster.duty import DUTY_DESCRIPTION_MAX, load_duty, template_path

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
